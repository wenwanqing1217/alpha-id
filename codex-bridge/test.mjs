import http from "http";
const AUTH = "sk-proxy-local-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4";

function req(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const opts = {
      hostname: "127.0.0.1", port: 4000, path, method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${AUTH}`, "Content-Length": Buffer.byteLength(data) },
    };
    const r = http.request(opts, (res) => {
      let d = "";
      res.on("data", (c) => (d += c));
      res.on("end", () => resolve({ status: res.statusCode, body: JSON.parse(d) }));
    });
    r.on("error", reject);
    r.write(data);
    r.end();
  });
}

async function main() {
  // 1. Simple Responses API
  console.log("=== Test 1: Simple Responses API ===");
  let r = await req("/v1/responses", { model: "deepseek-v4-flash", input: [{ role: "user", content: "say hi" }], max_output_tokens: 50 });
  console.log("  Status:", r.status);
  if (r.status === 200) console.log("  OK:", (r.body.output?.[0]?.content?.[0]?.text || "").slice(0, 80));

  // 2. Tool call
  console.log("\n=== Test 2: Tool call ===");
  r = await req("/v1/responses", {
    model: "deepseek-v4-flash",
    input: [{ role: "user", content: "get current profile" }],
    tools: [{ type: "function", name: "get_profile", description: "Get user profile", parameters: { type: "object", properties: {} } }],
    max_output_tokens: 500,
  });
  console.log("  Status:", r.status);
  if (r.status === 200) {
    const calls = r.body.output?.filter((o) => o.type === "function_call");
    if (calls?.length) console.log("  Tool call:", calls[0].name, calls[0].arguments);
    else console.log("  Content:", (r.body.output?.[0]?.content?.[0]?.text || "").slice(0, 80));
  } else {
    console.log("  Error:", JSON.stringify(r.body).slice(0, 400));
  }

  // 3. Tool call with round-trip (assistant with tool_calls -> tool result)
  console.log("\n=== Test 3: Tool call with round-trip ===");
  const input = [
    { role: "user", content: "what is the weather in Beijing?" },
    { role: "assistant", content: null, tool_calls: [{ id: "tc1", type: "function", function: { name: "get_weather", arguments: '{"city":"Beijing"}' } }] },
  ];
  r = await req("/v1/responses", {
    model: "deepseek-v4-flash",
    input,
    tools: [{ type: "function", name: "get_weather", description: "Get weather", parameters: { type: "object", properties: { city: { type: "string" } }, required: ["city"] } }],
    max_output_tokens: 500,
  });
  console.log("  Status:", r.status);
  if (r.status === 200) {
    const calls = r.body.output?.filter((o) => o.type === "function_call");
    if (calls?.length) console.log("  Tool call:", calls[0].name, calls[0].arguments);
    else console.log("  Content:", (r.body.output?.[0]?.content?.[0]?.text || "").slice(0, 80));
  } else {
    console.log("  Error:", JSON.stringify(r.body).slice(0, 500));
  }

  // 4. The original failing scenario: assistant tool_calls without reasoning_content
  console.log("\n=== Test 4: Original failing scenario (assistant tool_calls w/o reasoning) ===");
  r = await req("/v1/responses", {
    model: "deepseek-v4-flash",
    input: [
      { role: "user", content: "search for deepseek news" },
      { role: "assistant", content: null, tool_calls: [{ id: "call_1", type: "function", function: { name: "web_search", arguments: '{"query":"deepseek 2025"}' } }] },
      { role: "tool", tool_call_id: "call_1", content: "DeepSeek released v4 in 2025..." },
    ],
    tools: [{ type: "function", name: "web_search", description: "Search web", parameters: { type: "object", properties: { query: { type: "string" } }, required: ["query"] } }],
    max_output_tokens: 500,
  });
  console.log("  Status:", r.status);
  if (r.status === 200) {
    console.log("  Content:", (r.body.output?.[0]?.content?.[0]?.text || "").slice(0, 150));
  } else {
    console.log("  Error:", JSON.stringify(r.body).slice(0, 500));
  }
}

main().catch(console.error);
