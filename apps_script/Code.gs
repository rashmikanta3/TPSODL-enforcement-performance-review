const ROOT_FOLDER_ID = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX";
const API_SECRET = "XXXXXXXXXXXXXXXXXXXXXXXXXXXX"; // Pick any strong random password

function getOrCreateFolder(parentFolder, name) {
  const folders = parentFolder.getFoldersByName(name);
  if (folders.hasNext()) {
    return folders.next();
  }
  return parentFolder.createFolder(name);
}

function jsonResponse(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

// Handles Upload and Delete requests from FastAPI
function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    if (payload.secret !== API_SECRET) {
      return jsonResponse({ status: "error", message: "Unauthorized" });
    }

    // Action 1: Delete PVR file from Google Drive
    if (payload.action === "delete") {
      DriveApp.getFileById(payload.fileId).setTrashed(true);
      return jsonResponse({ status: "success", deleted: payload.fileId });
    }

    // Action 2: Upload PVR into Year / Month / Date / Team Leader folder
    const parts = payload.pvrDate.split("-"); // YYYY-MM-DD
    const year = parts[0];
    const month = parts[1];

    let folder = DriveApp.getFolderById(ROOT_FOLDER_ID);
    folder = getOrCreateFolder(folder, year);
    folder = getOrCreateFolder(folder, month);
    folder = getOrCreateFolder(folder, payload.pvrDate);
    folder = getOrCreateFolder(folder, payload.teamLeader);

    const bytes = Utilities.base64Decode(payload.fileBase64);
    const blob = Utilities.newBlob(bytes, "application/pdf", payload.filename);
    const file = folder.createFile(blob);

    return jsonResponse({
      status: "success",
      fileId: file.getId(),
      filename: file.getName(),
    });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}

// Handles View / Download requests from FastAPI
function doGet(e) {
  try {
    if (e.parameter.secret !== API_SECRET) {
      return jsonResponse({ status: "error", message: "Unauthorized" });
    }

    const file = DriveApp.getFileById(e.parameter.fileId);
    const blob = file.getBlob();
    const base64Data = Utilities.base64Encode(blob.getBytes());

    return jsonResponse({
      status: "success",
      filename: file.getName(),
      mimeType: blob.getContentType(),
      fileBase64: base64Data,
    });
  } catch (err) {
    return jsonResponse({ status: "error", message: err.toString() });
  }
}