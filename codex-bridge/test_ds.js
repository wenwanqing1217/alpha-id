const https = require('https');
const data = JSON.stringify({
  model: 'deepseek-v4-flash',
  messages: [{ role: 'user', content: 'hello' }],
  max_tokens: 50,
});
const req = https.request({
  hostname: 'api.deepseek.com', path: '/v1/chat/completions', method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer sk-fbc50acd7fa34231a845632e640ff653' }
}, res => {
  let body = '';
  res.on('data', c => body += c);
  res.on('end', () => {
    console.log('Status:', res.statusCode);
    console.log('Body:', body.slice(0, 300));
    process.exit(0);
  });
});
req.on('error', e => { console.log('Error:', e.message); process.exit(1); });
req.write(data);
req.end();
setTimeout(() => { console.log('TIMEOUT'); process.exit(1); }, 30000);
