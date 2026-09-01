import express from "express";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BOT = process.env.BOT_URL || "http://127.0.0.1:8787";
const PORT = process.env.PORT || 4000;

const app = express();
app.use(express.static(path.join(__dirname, "public")));

app.get("/api/state", async (_req, res) => {
  try {
    const r = await fetch(`${BOT}/state`);
    res.status(r.status).json(await r.json());
  } catch (e) {
    res.status(502).json({ error: `bot unreachable at ${BOT}: ${e}` });
  }
});

for (const route of ["halt", "resume"]) {
  app.post(`/api/${route}`, async (_req, res) => {
    try {
      const r = await fetch(`${BOT}/${route}`, { method: "POST" });
      res.status(r.status).json(await r.json());
    } catch (e) {
      res.status(502).json({ error: String(e) });
    }
  });
}

app.listen(PORT, () => console.log(`dashboard  http://localhost:${PORT}  ->  bot ${BOT}`));
