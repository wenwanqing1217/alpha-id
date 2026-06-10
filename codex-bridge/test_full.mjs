#!/usr/bin/env node
// Test codex-bridge with the correct auth key
import http from "node:http";

const HOST = "127.0.0.1";
const PORT = 4000;
const AUTH = "sk-proxy-local-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4";

function post(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = http.request(
      { hostname: HOST, port: PORT, path, method: "POST",
        headers: { "Content-Type": "application/json",
                   "Authorization": `Bearer ${AUTH}`,
                   "Content-Length": data.length }},
      (res) => {
        let body = "";
        res.on("data", (c) => body += c);
        res.on("end", () => resolve({ status: res.statusCode, body: JSON.parse(body) }));
      }
    );
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

async function main() {
  // Test 1: Simple Responses API
  console.log("=== Test 1: Simple Responses API ===");
  let r = await post("/v1/responses", {
    model: "deepseek-v4-flash",
    input: [{ role: "user", content: "say hello" }],
    max_tokens: 50,
  });
  console.log(`  Status: ${r.status}`);
  if (r.status === 200) console.log(`  Content: ${r.body.output?.[0]?.content?.[0]?.text?.slice(0,80)}`);
  else console.log(`  Error: ${JSON.stringify(r.body).slice(0,200)}`);

  // Test 2: Responses API + function tools
  console.log("\n=== Test 2: Responses API + function tools ===");
  r = await post("/v1/responses", {
    model: "deepseek-v4-flash",
    input: [{ role: "user", content: "帮我查一下我的身份信息" }],
    tools: [
      {
        type: "function",
        name: "get_profile",
        description: "获取当前用户的身份信息",
        parameters: { type: "object", properties: {} }
      }
    ],
    tool_choice: "auto",
    max_tokens: 300,
  });
  console.log(`  Status: ${r.status}`);
  if (r.status === 200) {
    const out = r.body.output?.[0];
    if (out?.type === "function_call") {
      console.log(`  Tool call: ${out.name}(${JSON.stringify(out.arguments)})`);
    } else {
      console.log(`  Output: ${JSON.stringify(out).slice(0,200)}`);
    }
  } else {
    console.log(`  Error: ${JSON.stringify(r.body).slice(0,300)}`);
  }

  // Test 3: Chat Completions API (standard format)
  console.log("\n=== Test 3: Chat Completions API ===");
  r = await post("/v1/chat/completions", {
    model: "deepseek-v4-flash",
    messages: [{ role: "user", content: "what's 2+2?" }],
    max_tokens: 50,
  });
  console.log(`  Status: ${r.status}`);
  if (r.status === 200) console.log(`  Content: ${r.body.choices?.[0]?.message?.content?.slice(0,80)}`);
  else console.log(`  Error: ${JSON.stringify(r.body).slice(0,200)}`);

  console.log("\nDone.");
}

main().catch(console.error);
