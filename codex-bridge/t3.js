const http = require('http');
const HOST = '127.0.0.1', PORT = 4000;
const AUTH = 'Bearer sk-proxy-local-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4';

function post(path, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = http.request({ hostname: HOST, port: PORT, path, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': AUTH } },
      res => { let b = ''; res.on('data', c => b += c); res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(b) })); }
    );
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function main() {
  // Test 1: Simple chat
  console.log('=== Test 1: Simple Responses API ===');
  let r = await post('/v1/responses', { model:'deepseek-v4-flash', input:[{role:'user',content:'hello'}], max_tokens:50 });
  console.log('Status:', r.status);
  if (r.status===200) console.log('OK:', (r.body.output?.[0]?.content?.[0]?.text||'').slice(0,80));
  else console.log('ERR:', JSON.stringify(r.body).slice(0,200));

  // Test 2: Chat Completions with tools
  console.log('\n=== Test 2: Chat Completions + tools ===');
  r = await post('/v1/chat/completions', {
    model:'deepseek-v4-flash',
    messages:[{role:'user',content:'say hello and use get_profile tool'}],
    tools:[{type:'function',function:{name:'get_profile',description:'get profile',parameters:{type:'object',properties:{}}}}],
    tool_choice:'auto', max_tokens:200
  });
  console.log('Status:', r.status);
  if (r.status===200) {
    const m = r.body.choices?.[0]?.message;
    if (m?.tool_calls) console.log('TOOL_CALL:', m.tool_calls.map(t=>t.function.name+'('+t.function.arguments+')').join(', '));
    else console.log('TEXT:', (m?.content||'').slice(0,100));
  } else console.log('ERR:', JSON.stringify(r.body).slice(0,300));

  // Test 3: Responses API + tools (the original problem)
  console.log('\n=== Test 3: Responses API + tools ===');
  r = await post('/v1/responses', {
    model:'deepseek-v4-flash',
    input:[{role:'user',content:'say hello and use get_profile tool'}],
    tools:[{type:'function',name:'get_profile',description:'get profile',parameters:{type:'object',properties:{}}}],
    tool_choice:'auto', max_tokens:200
  });
  console.log('Status:', r.status);
  if (r.status===200) {
    const o = r.body.output?.[0];
    if (o?.type==='function_call') console.log('TOOL_CALL:', o.name, JSON.stringify(o.arguments));
    else console.log('TEXT:', (o?.content?.[0]?.text||'').slice(0,100));
  } else console.log('ERR:', JSON.stringify(r.body).slice(0,300));
}

main().catch(e => { console.log('FAIL:', e.message); process.exit(1); });
