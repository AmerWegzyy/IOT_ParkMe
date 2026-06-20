# Inline Base64 Image Storage Changes

This document outlines the modifications made to transition from Firebase Storage to inline Base64 Firestore document storage for violation snapshots.

## 1. `Backend/main.py`
* **Added Imports**: Added `import base64` at the top.
* **Removed Firebase Storage logic**: Removed all instances of `storage.bucket()` and `blob.upload_from_string()` / `blob.delete()`.
* **Added Base64 Encoding**: In `receive_park_event`, the incoming `image_bytes` are now encoded into a `data:image/jpeg;base64,...` string.
* **Updated Dictionary Keys**: Replaced all usages of `image_url` and `image_path` with `image_data`. The Base64 string is now saved directly into the `parking_logs` Firestore document.
* **Updated Bouncy Driver Cleanup**: In `receive_heartbeat_data` (and the bulk cleanup fallback), it now simply uses `firestore.DELETE_FIELD` on `image_data` instead of calling out to Firebase Storage to delete a blob.

## 2. `Frontend/app.js`
* **Updated Variable Name**: In the `appendLog` function, changed the check from `${log.image_url ? ...}` to `${log.image_data ? ...}`. The data URI is passed directly into the `openImageModal` function.

## 3. `Frontend/index.html` & `Frontend/style.css`
* **No changes needed**: The existing HTML (`<img id="modal-image" src="" />`) and CSS natively support Base64 Data URIs injected into the `src` attribute. The browser renders them exactly the same as remote HTTP URLs, so the UI code did not need to be refactored.

---
**Note for merging**: If the incoming teammate's server-centered changes modify `receive_park_event` or how the camera polls for capture commands, simply ensure that when the picture is eventually uploaded, it uses `base64.b64encode()` and saves to the `"image_data"` key in Firestore rather than uploading to a storage bucket.
