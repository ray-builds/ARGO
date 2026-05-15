const express = require("express");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

const PORT = Number(process.env.BRIDGE_PORT || 3001);
const ARGO_BACKEND_URL = process.env.ARGO_BACKEND_URL || "http://app:8000";
const BRIDGE_SECRET = process.env.BRIDGE_SECRET || "";
const MAX_HISTORY_PER_CHAT = Number(process.env.BRIDGE_MAX_HISTORY || 500);
const ALLOWED_GROUP_IDS = (process.env.BRIDGE_ALLOWED_GROUP_IDS || "")
  .split(",")
  .map((v) => v.trim())
  .filter(Boolean);
const ALLOWED_GROUP_NAMES = (process.env.BRIDGE_ALLOWED_GROUP_NAMES || "")
  .split(",")
  .map((v) => v.trim().toLowerCase())
  .filter(Boolean);

const app = express();
app.use(express.json({ limit: "1mb" }));

let isReady = false;
const messageHistory = new Map();

const client = new Client({
  authStrategy: new LocalAuth({ clientId: "argo-bridge" }),
  puppeteer: {
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"]
  }
});

function rememberMessage(chatId, payload) {
  if (!chatId) return;
  const current = messageHistory.get(chatId) || [];
  current.push(payload);
  if (current.length > MAX_HISTORY_PER_CHAT) {
    current.splice(0, current.length - MAX_HISTORY_PER_CHAT);
  }
  messageHistory.set(chatId, current);
}

async function forwardToArgo(payload) {
  const headers = { "Content-Type": "application/json" };
  if (BRIDGE_SECRET) {
    headers["X-Bridge-Secret"] = BRIDGE_SECRET;
  }

  const response = await fetch(`${ARGO_BACKEND_URL}/api/whatsapp/incoming`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`ARGO ingest failed (${response.status}): ${body}`);
  }
}

function isAllowedGroup(groupId, groupName) {
  if (!ALLOWED_GROUP_IDS.length && !ALLOWED_GROUP_NAMES.length) {
    return true;
  }
  if (ALLOWED_GROUP_IDS.includes(groupId)) {
    return true;
  }
  if (groupName && ALLOWED_GROUP_NAMES.includes(String(groupName).toLowerCase())) {
    return true;
  }
  return false;
}

client.on("qr", (qr) => {
  console.log("Scan this QR to connect WhatsApp:");
  qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
  isReady = true;
  console.log("WhatsApp bridge connected.");
});

client.on("auth_failure", (msg) => {
  console.error("WhatsApp auth failure:", msg);
  isReady = false;
});

client.on("disconnected", (reason) => {
  console.warn("WhatsApp bridge disconnected:", reason);
  isReady = false;
});

client.on("message", async (msg) => {
  try {
    const isGroup = msg.from.endsWith("@g.us");
    if (!isGroup) {
      return;
    }

    const chat = await msg.getChat();
    if (!isAllowedGroup(msg.from, chat.name)) {
      return;
    }

    const payload = {
      id: msg.id?._serialized || `${msg.from}-${msg.timestamp}`,
      from: msg.from,
      to: msg.to,
      body: msg.body || "",
      timestamp: msg.timestamp,
      author: msg.author || msg.from,
      isGroup,
      groupName: isGroup ? chat.name : null
    };

    rememberMessage(msg.from, payload);
    await forwardToArgo(payload);
  } catch (err) {
    console.error("Failed processing inbound WhatsApp message:", err.message);
  }
});

app.get("/health", (_req, res) => {
  res.json({
    status: isReady ? "ready" : "initializing",
    ready: isReady,
    backend: ARGO_BACKEND_URL,
    allowedGroupIds: ALLOWED_GROUP_IDS,
    allowedGroupNames: ALLOWED_GROUP_NAMES
  });
});

app.get("/messages/:groupId", async (req, res) => {
  try {
    const groupId = req.params.groupId;
    if (!groupId) {
      return res.status(400).json({ detail: "groupId required" });
    }

    const cached = messageHistory.get(groupId);
    if (cached && cached.length) {
      return res.json(cached);
    }

    if (!isReady) {
      return res.status(503).json({ detail: "WhatsApp client not ready yet" });
    }

    const chat = await client.getChatById(groupId);
    const messages = await chat.fetchMessages({ limit: MAX_HISTORY_PER_CHAT });
    const normalized = messages.map((m) => ({
      id: m.id?._serialized,
      body: m.body || "",
      timestamp: m.timestamp,
      author: m.author || m.from
    }));
    return res.json(normalized);
  } catch (err) {
    return res.status(500).json({ detail: `Failed to fetch messages: ${err.message}` });
  }
});

app.get("/groups", async (_req, res) => {
  try {
    if (!isReady) {
      return res.status(503).json({ detail: "WhatsApp client not ready yet" });
    }
    const chats = await client.getChats();
    const groups = chats
      .filter((c) => c.isGroup)
      .map((c) => ({
        id: c.id?._serialized || c.id?.user || "",
        name: c.name || ""
      }));
    return res.json(groups);
  } catch (err) {
    return res.status(500).json({ detail: `Failed to list groups: ${err.message}` });
  }
});

app.listen(PORT, () => {
  console.log(`WhatsApp bridge API listening on port ${PORT}`);
  client.initialize();
});
