/**
 * TPSODL PVR - Google Apps Script Web App (control plane for Google Drive).
 *
 * Deploy: Deploy > Manage deployments > Edit (pencil) > Version: "New version" > Deploy
 *         Execute as: Me      Who has access: Anyone
 * Script property (Project Settings > Script properties):  SECRET = <same as GOOGLE_APPS_SCRIPT_SECRET>
 *
 * Actions (POST JSON, every request must carry "secret"):
 *   token   -> { status, accessToken, expiresIn }          short-lived OAuth token for the Drive REST API
 *   folder  -> { status, folderId }                          pvrDate (YYYY-MM-DD), teamLeader
 *   move    -> { status, fileId, folderId }                  fileId, pvrDate, teamLeader, newName
 *   upload  -> { status, fileId, folderId }                  fallback: pvrDate, teamLeader, filename, fileBase64
 *   delete  -> { status }                                    fileId (moves to trash)
 * GET ?secret=..&fileId=..  -> { status, fileBase64, ... } fallback download
 *
 * Every file operation is limited to files inside the TPSODL_PVR folder tree.
 * Folder layout: TPSODL_PVR / YYYY / MM-MonthName / DD-MM-YYYY / <Team Leader>
 */

var ROOT_NAME = 'TPSODL_PVR';
var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
              'August', 'September', 'October', 'November', 'December'];
var CACHE_SECONDS = 21600; // 6 h (CacheService maximum)

// This script uses DriveApp (e.g. DriveApp.getRootFolder() in rootFolder_), so Apps Script
// grants it the full Drive scope and the token from action "token" can call the Drive REST API.
// After pasting a new version, run any function once in the editor if it asks to re-authorize.

function doPost(e) {
  try {
    var body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    checkSecret_(body.secret);
    switch (body.action) {
      case 'token':  return json_({ status: 'success', accessToken: ScriptApp.getOAuthToken(), expiresIn: 3000 });
      case 'folder': return json_({ status: 'success', folderId: pvrFolder_(body.pvrDate, body.teamLeader).getId() });
      case 'move':   return json_(moveFile_(body));
      case 'upload': return json_(uploadFile_(body));
      case 'delete': return json_(deleteFile_(body));
      default:       return json_({ status: 'error', message: 'Unknown action: ' + body.action });
    }
  } catch (err) {
    return json_({ status: 'error', message: String(err && err.message || err) });
  }
}

function doGet(e) {
  try {
    var p = (e && e.parameter) || {};
    checkSecret_(p.secret);
    if (!p.fileId) throw new Error('fileId is required');
    var file = pvrFile_(p.fileId);
    var blob = file.getBlob();
    return json_({ status: 'success', fileId: file.getId(), fileName: file.getName(),
                   mimeType: blob.getContentType(), fileBase64: Utilities.base64Encode(blob.getBytes()) });
  } catch (err) {
    return json_({ status: 'error', message: String(err && err.message || err) });
  }
}

// ---------------------------------------------------------------------------
function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function checkSecret_(secret) {
  var expected = PropertiesService.getScriptProperties().getProperty('SECRET');
  if (!expected) throw new Error('Script property SECRET is not set');
  if (!secret || secret !== expected) throw new Error('Unauthorized');
}

function sanitize_(name) {
  var s = String(name || '').replace(/[\\\/:*?"<>|\u0000-\u001f]+/g, '').replace(/\s+/g, ' ').trim();
  s = s.replace(/^\.+|\.+$/g, '').trim();
  return s.substring(0, 120).trim() || 'Unnamed';
}

function folderParts_(pvrDate, teamLeader) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(pvrDate || ''));
  if (!m) throw new Error('pvrDate must be YYYY-MM-DD');
  var monthIdx = parseInt(m[2], 10) - 1;
  if (monthIdx < 0 || monthIdx > 11) throw new Error('Invalid month in pvrDate');
  return [m[1], m[2] + '-' + MONTHS[monthIdx], m[3] + '-' + m[2] + '-' + m[1], sanitize_(teamLeader)];
}

// ---------------------------------------------------------------------------
// Folders with a cache (CacheService + Script Properties) so repeat calls skip the walk
// ---------------------------------------------------------------------------
function cachedFolder_(key) {
  var id = CacheService.getScriptCache().get(key) || PropertiesService.getScriptProperties().getProperty(key);
  if (!id) return null;
  try {
    var f = DriveApp.getFolderById(id);
    if (!f.isTrashed()) return f;
  } catch (e) { /* deleted */ }
  PropertiesService.getScriptProperties().deleteProperty(key);
  CacheService.getScriptCache().remove(key);
  return null;
}

function remember_(key, folder) {
  CacheService.getScriptCache().put(key, folder.getId(), CACHE_SECONDS);
  PropertiesService.getScriptProperties().setProperty(key, folder.getId());
}

function childFolder_(parent, name) {
  var it = parent.getFoldersByName(name);
  while (it.hasNext()) {
    var f = it.next();
    if (!f.isTrashed()) return f;
  }
  return parent.createFolder(name);
}

function rootFolder_() {
  var key = 'folder:' + ROOT_NAME;
  var f = cachedFolder_(key);
  if (f) return f;
  f = childFolder_(DriveApp.getRootFolder(), ROOT_NAME);
  remember_(key, f);
  return f;
}

function pvrFolder_(pvrDate, teamLeader) {
  var parts = folderParts_(pvrDate, teamLeader);
  var key = 'folder:' + ROOT_NAME + '/' + parts.join('/');
  var cached = cachedFolder_(key);
  if (cached) return cached;

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);                       // no twin folders from parallel requests
  try {
    cached = cachedFolder_(key);
    if (cached) return cached;
    var folder = rootFolder_();
    var path = ROOT_NAME;
    for (var i = 0; i < parts.length; i++) {
      path += '/' + parts[i];
      var k = 'folder:' + path;
      var c = cachedFolder_(k);
      folder = c || childFolder_(folder, parts[i]);
      if (!c) remember_(k, folder);
    }
    return folder;
  } finally {
    lock.releaseLock();
  }
}

// ---------------------------------------------------------------------------
// Files (only inside TPSODL_PVR)
// ---------------------------------------------------------------------------
function isInsideRoot_(file) {
  var rootId = rootFolder_().getId();
  var queue = [];
  var parents = file.getParents();
  while (parents.hasNext()) queue.push({ f: parents.next(), d: 0 });
  while (queue.length) {
    var item = queue.shift();
    if (item.f.getId() === rootId) return true;
    if (item.d >= 6) continue;
    var up = item.f.getParents();
    while (up.hasNext()) queue.push({ f: up.next(), d: item.d + 1 });
  }
  return false;
}

function pvrFile_(fileId) {
  var file;
  try { file = DriveApp.getFileById(fileId); } catch (e) { throw new Error('File not found: ' + fileId); }
  if (file.isTrashed()) throw new Error('File not found (trashed): ' + fileId);
  if (!isInsideRoot_(file)) throw new Error('Access denied: file is outside ' + ROOT_NAME);
  return file;
}

function moveFile_(b) {
  if (!b.fileId) throw new Error('fileId is required');
  var file = pvrFile_(b.fileId);
  var folder = pvrFolder_(b.pvrDate, b.teamLeader);
  file.moveTo(folder);
  if (b.newName) file.setName(String(b.newName));
  return { status: 'success', fileId: file.getId(), folderId: folder.getId() };
}

function uploadFile_(b) {
  if (!b.fileBase64) throw new Error('fileBase64 is required');
  var folder = pvrFolder_(b.pvrDate, b.teamLeader);
  var blob = Utilities.newBlob(Utilities.base64Decode(b.fileBase64), 'application/pdf',
                               String(b.filename || 'PVR.pdf'));
  var file = folder.createFile(blob);
  return { status: 'success', fileId: file.getId(), folderId: folder.getId() };
}

function deleteFile_(b) {
  if (!b.fileId) throw new Error('fileId is required');
  pvrFile_(b.fileId).setTrashed(true);
  return { status: 'success' };
}
