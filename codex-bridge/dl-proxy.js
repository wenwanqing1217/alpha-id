const https = require("https");
const fs = require("fs");

const TOKEN = process.env.GH_TOKEN || "";
const opts = {
  hostname: "api.github.com",
  path: "/repos/wujfeng712-ui/codex-bridge/contents/proxy.mjs",
  headers: {
    "User-Agent": "codex-bridge-installer",
    Accept: "application/vnd.github.raw",
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
  },
};

https.get(opts, (res) => {
  if (res.statusCode !== 200) {
    console.error("HTTP", res.statusCode);
    res.pipe(process.stderr);
    process.exit(1);
  }
  const file = fs.createWriteStream(process.argv[2] || "proxy.mjs");
  res.pipe(file);
  file.on("finish", () => {
    console.log("Downloaded OK");
    process.exit(0);
  });
}).on("error", (e) => {
  console.error("Error:", e.message);
  process.exit(1);
});
