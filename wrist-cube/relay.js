#!/usr/bin/env node
// Bilek Küpü relay: saatten gelen WebSocket mesajlarını tarayıcıya aktarır.
// Bağımlılık yok. Çalıştır:  node relay.js   (port değiştirmek için: PORT=9000 node relay.js)
// Aynı port üzerinden index.html'i de sunar: http://<bilgisayar-ip>:8765
'use strict';
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const os = require('os');

const PORT = Number(process.env.PORT) || 8765;
const MAX_PAYLOAD = 64 * 1024;
const clients = new Set();
let nextId = 1;

const server = http.createServer((req, res) => {
  const url = (req.url || '/').split('?')[0];
  if (url !== '/' && url !== '/index.html') { res.writeHead(404); res.end('Bulunamadı'); return; }
  fs.readFile(path.join(__dirname, 'index.html'), (err, data) => {
    if (err) { res.writeHead(500); res.end('index.html okunamadı'); return; }
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    res.end(data);
  });
});

function frame(payload, opcode = 0x1) {
  const n = payload.length;
  let head;
  if (n < 126) head = Buffer.from([0x80 | opcode, n]);
  else if (n < 65536) { head = Buffer.alloc(4); head[0] = 0x80 | opcode; head[1] = 126; head.writeUInt16BE(n, 2); }
  else { head = Buffer.alloc(10); head[0] = 0x80 | opcode; head[1] = 127; head.writeBigUInt64BE(BigInt(n), 2); }
  return Buffer.concat([head, payload]);
}

function broadcast(from, payload) {
  const data = frame(payload);
  for (const c of clients) {
    if (c === from || !c.sock.writable) continue;
    if (c.sock.writableLength > 256 * 1024) continue; // yavaş istemci: kare atla
    c.sock.write(data);
  }
  from.count++;
}

function drop(c) {
  if (!clients.delete(c)) return;
  console.log(`- istemci #${c.id} ayrıldı (${clients.size} bağlı)`);
  c.sock.destroy();
}

function parse(c) {
  for (;;) {
    const b = c.buf;
    if (b.length < 2) return;
    const opcode = b[0] & 0x0f;
    const masked = (b[1] & 0x80) !== 0;
    let len = b[1] & 0x7f, off = 2;
    if (len === 126) { if (b.length < 4) return; len = b.readUInt16BE(2); off = 4; }
    else if (len === 127) { if (b.length < 10) return; len = Number(b.readBigUInt64BE(2)); off = 10; }
    if (len > MAX_PAYLOAD) { drop(c); return; }
    const maskLen = masked ? 4 : 0;
    if (b.length < off + maskLen + len) return;
    let payload = Buffer.from(b.subarray(off + maskLen, off + maskLen + len));
    if (masked) { const m = b.subarray(off, off + 4); for (let i = 0; i < payload.length; i++) payload[i] ^= m[i & 3]; }
    c.buf = b.subarray(off + maskLen + len);

    if (opcode === 0x8) { c.sock.end(frame(Buffer.alloc(0), 0x8)); drop(c); return; }
    if (opcode === 0x9) { c.sock.write(frame(payload, 0xA)); continue; }
    if (opcode === 0x1) broadcast(c, payload);
  }
}

server.on('upgrade', (req, sock) => {
  const key = req.headers['sec-websocket-key'];
  if (!key || String(req.headers.upgrade).toLowerCase() !== 'websocket') { sock.destroy(); return; }
  const accept = crypto.createHash('sha1').update(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest('base64');
  sock.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ' + accept + '\r\n\r\n');
  sock.setNoDelay(true);
  const c = { id: nextId++, sock, buf: Buffer.alloc(0), count: 0, ua: String(req.headers['user-agent'] || '').slice(0, 40) };
  clients.add(c);
  console.log(`+ istemci #${c.id} bağlandı (${clients.size} bağlı) ${c.ua}`);
  sock.on('data', d => { c.buf = c.buf.length ? Buffer.concat([c.buf, d]) : d; parse(c); });
  sock.on('close', () => drop(c));
  sock.on('error', () => drop(c));
});

setInterval(() => {
  for (const c of clients) {
    if (c.count) console.log(`  #${c.id}: ${c.count} mesaj/5 sn`);
    c.count = 0;
  }
}, 5000).unref();

server.listen(PORT, '0.0.0.0', () => {
  const ips = Object.values(os.networkInterfaces()).flat().filter(i => i && i.family === 'IPv4' && !i.internal).map(i => i.address);
  console.log(`Bilek Küpü relay ${PORT} portunda çalışıyor.`);
  for (const ip of ips.length ? ips : ['localhost']) {
    console.log(`  Tarayıcı:  http://${ip}:${PORT}`);
    console.log(`  Saat:      ws://${ip}:${PORT}/ws`);
  }
});
