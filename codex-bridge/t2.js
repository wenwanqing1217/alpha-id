const http = require('http');
const data = JSON.stringify({
  model: 'deepseek-v4-flash',
  input: [{ role: 'user', content: 'say hello' }],
  tools: [{ type: 'function', name: 'get_profile', description: 'get user profile', parameters: { type: 'object', properties: {} } }],
  tool_choice: 'auto',
  max_tokens: 200,
});
const req = http.request({
  hostname: '127.0.0.1', port: 4000, path: '/v1/responses', method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer sk-proxy-local-a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4' }
}, res => {
  let body = '';
  res.on('data', c => body += c);
  res.on('end', () => {
    const j = JSON.parse(body);
    const o = j.output?.[0];
    if (o?.type === 'function_call') console.log('TOOL_CALL:', o.name, JSON.stringify(o.arguments));
    else console.log('TEXT:', (o?.content?.[0]?.text || '').slice(0, 100));
    process.exit(0);
  });
});
req.on('error', e => { console.log('ERROR:', e.message); process.exit(1); });
req.write(data);
req.end();
setTimeout(() => { console.log('TIMEOUT'); process.exit(1); }, 90000);
