const PLUGIN_ID = "{7f9c5a2e-1d4b-4a8f-9c6e-2b3d5f7a9c10}";
const PLUGIN_VERSION = "1.1.0";
const IMPORT_ENDPOINT = "/ai-literature-management/link-import";
const HEALTH_ENDPOINT = "/ai-literature-management/link-import/health";
const TOKEN_PREF = "extensions.zotero-link-import.token";
const INSTALL_TOKEN = "__INSTALL_TOKEN__";
const ALLOWED_ROOT = __ALLOWED_ROOT__;

class ImportFailure extends Error {
  constructor(code, message, status = 400, details = {}) {
    super(message);
    this.name = "ImportFailure";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function response(status, body) {
  return [status, "application/json", JSON.stringify(body)];
}

function normalizeDOI(value) {
  return String(value || "")
    .trim()
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .replace(/^doi:\s*/i, "")
    .toLowerCase();
}

function normalizeTitle(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function normalizePath(value) {
  return String(value || "").replace(/\//g, "\\").toLowerCase();
}

function validateFile(path) {
  if (!path || typeof path !== "string") {
    throw new ImportFailure("invalid_path", "A PDF path is required");
  }

  let file;
  let root;
  try {
    file = Zotero.File.pathToFile(path);
    file.normalize();
    root = Zotero.File.pathToFile(ALLOWED_ROOT);
    root.normalize();
  }
  catch (error) {
    throw new ImportFailure("invalid_path", "The PDF path is invalid");
  }

  let rootPrefix = normalizePath(root.path).replace(/[\\]+$/, "") + "\\";
  let filePath = normalizePath(file.path);
  if (!filePath.startsWith(rootPrefix)) {
    throw new ImportFailure("invalid_path", "The PDF must be inside the configured literature root");
  }
  if (!file.exists() || !file.isFile() || !file.leafName.toLowerCase().endsWith(".pdf")) {
    throw new ImportFailure("invalid_path", "The requested PDF does not exist or is not a regular PDF file");
  }
  return file;
}

function findCollection(name) {
  if (!name || typeof name !== "string") {
    throw new ImportFailure("collection_not_found", "A collection name is required");
  }
  let target = name.trim().toLowerCase();
  let collections = Zotero.Collections.getByLibrary(
    Zotero.Libraries.userLibraryID,
    true,
    false
  ).filter(collection => collection.name.trim().toLowerCase() === target);

  if (!collections.length) {
    throw new ImportFailure("collection_not_found", `Collection '${name}' was not found`, 404);
  }
  if (collections.length > 1) {
    throw new ImportFailure(
      "ambiguous_collection",
      `Collection name '${name}' is ambiguous`,
      409,
      { matches: collections.map(collection => ({ key: collection.key, name: collection.name })) }
    );
  }
  return collections[0];
}

async function getLibraryItems() {
  return Zotero.Items.getAll(Zotero.Libraries.userLibraryID, false, false);
}

async function findExisting(items, doi, path, title) {
  let parentByDOI = null;
  let parentByTitle = null;
  let attachmentByPath = null;
  let targetPath = normalizePath(path);
  let targetTitle = normalizeTitle(title);

  for (let item of items) {
    if (item.isRegularItem()) {
      if (!parentByDOI && doi && normalizeDOI(item.getField("DOI")) === doi) {
        parentByDOI = item;
      }
      if (!parentByTitle && !doi && targetTitle
          && normalizeTitle(item.getField("title")) === targetTitle) {
        parentByTitle = item;
      }
      continue;
    }

    if (!attachmentByPath && item.isAttachment()
        && item.attachmentLinkMode === Zotero.Attachments.LINK_MODE_LINKED_FILE) {
      let existingPath = item.getFilePath();
      if (existingPath && normalizePath(existingPath) === targetPath) {
        attachmentByPath = item;
      }
    }
  }

  return { parentByDOI, parentByTitle, attachmentByPath };
}

async function addToCollection(item, collection, actions) {
  if (!item.inCollection(collection.id)) {
    item.addToCollection(collection.id);
    await item.saveTx({ skipDateModifiedUpdate: true });
    actions.push("added_item_to_collection");
  }
}

async function createParentFromDOI(doi, collection, createdIDs) {
  let beforeIDs = new Set(await Zotero.Items.getAll(
    Zotero.Libraries.userLibraryID,
    false,
    false,
    true
  ));

  try {
    let translate = new Zotero.Translate.Search();
    translate.setIdentifier({ DOI: doi });
    let translators = await translate.getTranslators();
    if (!translators.length) {
      throw new Error("No identifier translator accepted the DOI");
    }
    translate.setTranslator(translators);
    let items = await translate.translate({
      libraryID: Zotero.Libraries.userLibraryID,
      collections: [collection.id],
      saveAttachments: false
    });
    let parent = items.find(item => item.isRegularItem());
    if (!parent) {
      throw new Error("The DOI lookup returned no bibliographic item");
    }
    for (let item of items) {
      if (!beforeIDs.has(item.id)) createdIDs.push(item.id);
    }
    return parent;
  }
  catch (error) {
    let afterIDs = await Zotero.Items.getAll(
      Zotero.Libraries.userLibraryID,
      false,
      false,
      true
    );
    for (let id of afterIDs) {
      if (!beforeIDs.has(id) && !createdIDs.includes(id)) createdIDs.push(id);
    }
    throw new ImportFailure(
      "metadata_lookup_failed",
      `Zotero could not retrieve metadata for DOI ${doi}`,
      502,
      { cause: error.message }
    );
  }
}

async function linkAttachment(file, parent, collection, createdIDs) {
  let options = {
    file: file.path,
    title: "Full Text PDF",
    contentType: "application/pdf"
  };
  if (parent) {
    options.parentItemID = parent.id;
  }
  else {
    options.collections = [collection.id];
  }
  try {
    let attachment = await Zotero.Attachments.linkFromFile(options);
    createdIDs.push(attachment.id);
    return attachment;
  }
  catch (error) {
    throw new ImportFailure(
      "attachment_failed",
      "Zotero could not create the linked PDF attachment",
      500,
      { cause: error.message }
    );
  }
}

async function attachStandaloneToParent(attachment, parent, createdIDs) {
  attachment.parentItemID = parent.id;
  attachment.setCollections([]);
  await attachment.saveTx();
  if (!createdIDs.includes(attachment.id)) {
    return false;
  }
  return true;
}

async function recognizeAttachment(attachment, createdIDs) {
  let beforeIDs = new Set(await Zotero.Items.getAll(
    Zotero.Libraries.userLibraryID,
    false,
    false,
    true
  ));
  await Zotero.RecognizeDocument.recognizeItems([attachment]);
  let afterIDs = await Zotero.Items.getAll(
    Zotero.Libraries.userLibraryID,
    false,
    false,
    true
  );
  for (let id of afterIDs) {
    if (!beforeIDs.has(id) && !createdIDs.includes(id)) createdIDs.push(id);
  }
  return attachment.parentItemID ? await Zotero.Items.getAsync(attachment.parentItemID) : null;
}

async function rollback(createdIDs) {
  for (let id of [...createdIDs].reverse()) {
    try {
      let item = Zotero.Items.get(id);
      if (item) await item.eraseTx({ skipEditCheck: true });
    }
    catch (error) {
      Zotero.logError(error);
    }
  }
}

function buildResult(status, parent, attachment, collection, doi, file, metadataStatus, actions) {
  return {
    status,
    parent: parent ? { key: parent.key, title: parent.getField("title") } : null,
    attachment: attachment ? { key: attachment.key, linkMode: "linked_file" } : null,
    collection: { key: collection.key, name: collection.name },
    doi: doi || (parent ? normalizeDOI(parent.getField("DOI")) : ""),
    path: file.path,
    metadata_status: metadataStatus,
    actions
  };
}

async function importPDF(data) {
  let createdIDs = [];
  let actions = [];
  try {
    let file = validateFile(data.path);
    let collection = findCollection(data.collection);
    let doi = normalizeDOI(data.doi);
    if (doi && !/^10\.\d{4,9}\/\S+$/i.test(doi)) {
      throw new ImportFailure("invalid_doi", "The DOI format is invalid");
    }

    let items = await getLibraryItems();
    let existing = await findExisting(items, doi, file.path, data.title);
    let parent = existing.parentByDOI || existing.parentByTitle;
    let attachment = existing.attachmentByPath;

    if (attachment && attachment.parentItemID) {
      let attachmentParent = await Zotero.Items.getAsync(attachment.parentItemID);
      let attachmentDOI = normalizeDOI(attachmentParent.getField("DOI"));
      if (parent && parent.id !== attachmentParent.id
          || doi && attachmentDOI !== doi) {
        throw new ImportFailure(
          "duplicate_conflict",
          "The DOI and linked-file path refer to different Zotero items",
          409
        );
      }
      parent = attachmentParent;
      await addToCollection(parent, collection, actions);
      actions.push("reused_linked_attachment");
      return buildResult("reused", parent, attachment, collection, doi, file, "existing", actions);
    }

    if (!parent && doi) {
      parent = await createParentFromDOI(doi, collection, createdIDs);
      actions.push("created_parent_from_doi");
    }
    else if (parent) {
      await addToCollection(parent, collection, actions);
      actions.push("reused_parent");
    }

    if (attachment && !attachment.parentItemID && parent) {
      await attachStandaloneToParent(attachment, parent, createdIDs);
      actions.push("reused_and_attached_standalone_pdf");
      return buildResult("reused", parent, attachment, collection, doi, file, "existing", actions);
    }

    if (attachment && !attachment.parentItemID && !parent) {
      await addToCollection(attachment, collection, actions);
      actions.push("reused_standalone_linked_attachment");
      return buildResult(
        "reused",
        null,
        attachment,
        collection,
        doi,
        file,
        "unrecognized",
        actions
      );
    }

    if (!attachment) {
      attachment = await linkAttachment(file, parent, collection, createdIDs);
      actions.push("created_linked_attachment");
    }

    if (parent) {
      return buildResult("created", parent, attachment, collection, doi, file, "doi", actions);
    }

    parent = await recognizeAttachment(attachment, createdIDs);
    if (parent) {
      await addToCollection(parent, collection, actions);
      actions.push("recognized_pdf_metadata");
      return buildResult("created", parent, attachment, collection, doi, file, "recognized", actions);
    }

    actions.push("metadata_unrecognized");
    return buildResult(
      "partially_created",
      null,
      attachment,
      collection,
      doi,
      file,
      "unrecognized",
      actions
    );
  }
  catch (error) {
    await rollback(createdIDs);
    throw error;
  }
}

function registerEndpoints() {
  function HealthEndpoint() {}
  HealthEndpoint.prototype = {
    supportedMethods: ["GET"],
    init: async function (request) {
      return response(200, {
        status: "ok",
        plugin: PLUGIN_ID,
        version: PLUGIN_VERSION,
        allowed_root: ALLOWED_ROOT
      });
    }
  };

  function ImportEndpoint() {}
  ImportEndpoint.prototype = {
    supportedMethods: ["POST"],
    supportedDataTypes: ["application/json"],
    init: async function (request) {
      try {
        let token = request.headers["x-zotero-link-token"];
        let expected = Zotero.Prefs.get(TOKEN_PREF, true);
        if (!token || token !== expected) {
          throw new ImportFailure("unauthorized", "Invalid local import token", 401);
        }
        let result = await importPDF(request.data || {});
        return response(200, result);
      }
      catch (error) {
        if (error instanceof ImportFailure) {
          return response(error.status, {
            status: "error",
            error: error.code,
            message: error.message,
            details: error.details
          });
        }
        Zotero.logError(error);
        return response(500, {
          status: "error",
          error: "internal_error",
          message: "The Zotero import failed"
        });
      }
    }
  };

  Zotero.Server.Endpoints[HEALTH_ENDPOINT] = HealthEndpoint;
  Zotero.Server.Endpoints[IMPORT_ENDPOINT] = ImportEndpoint;
}

function install() {}

async function startup() {
  Zotero.Prefs.set(TOKEN_PREF, INSTALL_TOKEN, true);
  registerEndpoints();
  Zotero.debug(`${PLUGIN_ID} ${PLUGIN_VERSION} started`);
}

function onMainWindowLoad() {}
function onMainWindowUnload() {}

function shutdown(data, reason) {
  if (reason === APP_SHUTDOWN) return;
  delete Zotero.Server.Endpoints[HEALTH_ENDPOINT];
  delete Zotero.Server.Endpoints[IMPORT_ENDPOINT];
}

function uninstall() {}
