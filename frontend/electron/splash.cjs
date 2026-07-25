function splashHtml() {
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
    :root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;height:100vh;display:grid;place-items:center;overflow:hidden;background:#04060D;color:#E9EFFA;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
    body:before{content:"";position:absolute;inset:0;background:radial-gradient(280px 190px at 20% 0%,rgba(41,216,255,.12),transparent 62%),radial-gradient(300px 210px at 90% 0%,rgba(167,139,250,.1),transparent 65%)}
    .wrap{position:relative;display:flex;flex-direction:column;align-items:center;gap:12px}.name{font:600 12px ui-monospace,"SF Mono",monospace;letter-spacing:.34em}.status{font-size:11px;color:#5D6A85}.bar{width:150px;height:2px;overflow:hidden;border-radius:2px;background:#131B2D}.bar:before{content:"";display:block;width:40%;height:100%;background:#29D8FF;box-shadow:0 0 12px rgba(41,216,255,.5);animation:progress 1.6s ease-in-out infinite}@keyframes progress{from{transform:translateX(-100%)}to{transform:translateX(400%)}}
    @media(prefers-reduced-motion:reduce){*{animation:none!important}.bar:before{width:70%}}
  </style></head><body><div class="wrap"><svg width="46" height="46" viewBox="0 0 24 24" fill="none" aria-hidden="true"><polygon points="12,2.8 20,7.4 20,16.6 12,21.2 4,16.6 4,7.4" stroke="#29D8FF" stroke-width="1.7" stroke-linejoin="round"/><polyline points="7.6,15.4 10.8,11.8 13.6,13.4 16.6,8.8" stroke="#E9EFFA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".86"/><circle cx="16.6" cy="8.8" r="1.7" fill="#29D8FF"/></svg><div class="name">MAESTRO</div><div class="bar"></div><div class="status">正在准备运行时…</div></div></body></html>`;
}

module.exports = { splashHtml };
