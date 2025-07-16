const tesseract = require("tesseract.js");
const formidable = require("formidable");
const fs = require("fs");
const fetch = require("node-fetch");

const ZAPIER_URL = process.env.ZAPIER_WEBHOOK_URL || "";

module.exports = async (req, res) => {
  if (req.method !== "POST") return res.status(405).json({ error: "Only POST allowed" });

  const form = new formidable.IncomingForm();
  form.parse(req, async (err, fields, files) => {
    if (err) return res.status(500).json({ status: "parse-fail", reason: "File parse error" });

    const file = files.file;
    if (!file) return res.status(400).json({ status: "parse-fail", reason: "No file uploaded" });

    try {
      const text = await tesseract.recognize(file.filepath, "eng+fra");
      const parsed = parseTransactions(text.data.text, file.originalFilename);
      if (parsed.status === "parse-fail") return res.json(parsed);

      if (ZAPIER_URL) {
        try { await fetch(ZAPIER_URL, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(parsed) }); } catch {}
      }
      res.json(parsed);
    } catch (e) {
      res.status(500).json({ status: "parse-fail", reason: e.message });
    }
  });
};

function parseTransactions(text, filename) {
  const lines = text.split("\n").map(l => l.trim()).filter(l => l);
  const txns = [];
  const dateRx = /(\d{1,2})[\/\-\s](\d{1,2})(?:[\/\-\s](\d{2,4}))?/;
  const amountRx = /(-?\d+[\.,]\d{2})/;

  for (const l of lines) {
    const dateMatch = dateRx.exec(l);
    const amountMatch = amountRx.exec(l.replace(',', '.'));
    if (dateMatch && amountMatch) {
      let [_, d, m, y] = dateMatch;
      y = y || new Date().getFullYear();
      const dateStr = `${y}-${m.padStart(2, "0")}-${d.padStart(2, "0")}`;
      const desc = l.replace(dateRx, "").replace(amountRx, "").trim().slice(0, 60);
      txns.push({ date: dateStr, description: desc, amount: parseFloat(amountMatch[1].replace(',', '.')) });
    }
  }
  return txns.length
    ? txns
    : { status: "parse-fail", file: filename, reason: "No transactions found" };
}