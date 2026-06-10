import http from "http";
const AUTH = "sk-proxy-local-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4";
const BASE = { hostname: "127.0.0.1", port: 4000, headers: { "Content-Type": "application/json", "Authorization": `Bearer ${AUTH}` } };

function api(method, path, body) {
  return new Promise((resolve) => {
    const data = JSON.stringify(body);
    const opts = { ...BASE, path, method, headers: { ...BASE.headers, "Content-Length": Buffer.byteLength(data) } };
    const r = http.request(opts, (res) => { let d = ""; res.on("data", (c) => d += c); res.on("end", () => resolve({ status: res.statusCode, body: JSON.parse(d) })); });
    r.on("error", (e) => resolve({ status: 0, error: e.message }));
    r.write(data);
    r.end();
  });
}

const r = await api("POST", "/v1/responses", { model: "deepseek-v4-flash", input: [{ role: "user", content: "hi" }], max_output_tokens: 50 });
console.log("Status:", r.status);
if (r.body) console.log("Body:", JSON.stringify(r.body).slice(0, 300));
if (r.error) console.log("Error:", r.error);
