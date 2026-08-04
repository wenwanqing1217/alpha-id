// Ghost 前端逻辑 - 从 ghost.html 提取

document.addEventListener('DOMContentLoaded', function() {
  const reveals = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        // 每次进入视口都重新触发动画
        entry.target.classList.remove('visible');
        void entry.target.offsetWidth; // 强制重排
        entry.target.classList.add('visible');
      }
    });
  }, { threshold: 0.1, rootMargin: '-50px' });
  reveals.forEach(el => observer.observe(el));

  // ============ 小精灵互动系统 ============
  const alphaSprite = document.getElementById('alpha-sprite');
  const spriteBubble = document.getElementById('sprite-bubble');
  const bubbleText = document.getElementById('bubble-text');
  const rippleContainer = document.getElementById('ripple-container');

  // 有趣文案库
  const phrases = {
    near: ['被你发现了~', '星尘围绕着你', '因果在此交汇', '意识在苏醒', '连接已建立'],
    click: ['哇！你点我了！', '能量爆发~', '星轨在颤动', '灵魂在跳跃！', 'DID已激活'],
    doubleClick: ['(*^▽^*)', '开心到转圈~', '星光在闪耀', '宇宙在回应'],
    far: ['下次再见~', '星辰永不熄灭', '因果仍在延续', '我会在这里'],
    idle: ['等待指令...', '星尘在汇聚', '意识在漂移', '守护中...'],
    scroll: ['记忆在穿梭', '因果在编织', '探索更深的宇宙']
  };

  let bubbleTimeout;
  let idleTimeout;
  let lastClickTime = 0;
  let isNear = false;
  let isDragging = false;
  let spriteCurrentX = 0, spriteCurrentY = 0;

  // 显示气泡 - 在页面左上角或右上角区域安全显示，避免遮挡
  function showBubble(category) {
    const words = phrases[category];
    const word = words[Math.floor(Math.random() * words.length)];
    
    // 创建文字，逐个从左到右出现
    let html = '';
    for (let i = 0; i < word.length; i++) {
      html += `<span class="bubble-char" style="animation-delay: ${i * 0.15}s">${word[i]}</span>`;
    }
    bubbleText.innerHTML = html;
    
    const bubbleWidth = word.length * 20;
    const bubbleHeight = 36;
    
    // 随机选择左上角或右上角区域
    const isLeft = Math.random() > 0.5;
    
    // 获取当前滚动位置，确保气泡在可视区域内
    const scrollY = window.scrollY;
    const viewportHeight = window.innerHeight;
    const safeTop = scrollY + 100;
    const safeBottom = scrollY + viewportHeight - 100;
    
    if (isLeft) {
      // 左上角区域：页面左边15%
      spriteBubble.style.left = `${Math.random() * (window.innerWidth * 0.15 - bubbleWidth) + 20}px`;
      spriteBubble.style.top = `${safeTop + Math.random() * Math.min(viewportHeight * 0.4, safeBottom - safeTop - bubbleHeight)}px`;
      spriteBubble.style.right = 'auto';
    } else {
      // 右上角区域：页面右边15%
      spriteBubble.style.right = `${Math.random() * (window.innerWidth * 0.15 - bubbleWidth) + 20}px`;
      spriteBubble.style.top = `${safeTop + Math.random() * Math.min(viewportHeight * 0.4, safeBottom - safeTop - bubbleHeight)}px`;
      spriteBubble.style.left = 'auto';
    }
    
    spriteBubble.classList.add('visible');

    clearTimeout(bubbleTimeout);
    bubbleTimeout = setTimeout(() => {
      spriteBubble.classList.remove('visible');
    }, 5000);
  }

  // 创建涟漪
  function createRipple(x, y) {
    const ripple = document.createElement('div');
    ripple.className = 'ripple';
    ripple.style.left = (x - 50) + 'px';
    ripple.style.top = (y - 50) + 'px';
    ripple.style.width = '100px';
    ripple.style.height = '100px';
    rippleContainer.appendChild(ripple);

    setTimeout(() => {
      ripple.remove();
    }, 1000);
  }

  // 拖拽功能 - 支持随意拖拽并弹回原点
  if (alphaSprite) {
    let startX, startY;
    let velocityX = 0, velocityY = 0;

    alphaSprite.addEventListener('mousedown', (e) => {
      e.preventDefault();
      isDragging = true;
      startX = e.clientX - spriteCurrentX;
      startY = e.clientY - spriteCurrentY;
      alphaSprite.style.transition = 'none';
      alphaSprite.style.cursor = 'grabbing';
    });

    document.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      
      const newX = e.clientX - startX;
      const newY = e.clientY - startY;
      
      velocityX = newX - spriteCurrentX;
      velocityY = newY - spriteCurrentY;
      
      spriteCurrentX = newX;
      spriteCurrentY = newY;
      
      alphaSprite.style.transform = `translate(${spriteCurrentX}px, ${spriteCurrentY}px)`;
    });

    document.addEventListener('mouseup', () => {
      if (!isDragging) return;
      isDragging = false;
      alphaSprite.style.cursor = 'grab';
      
      // 弹回原点动画
      alphaSprite.style.transition = 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)';
      alphaSprite.style.transform = 'translate(0, 0)';
      
      spriteCurrentX = 0;
      spriteCurrentY = 0;
      
      setTimeout(() => {
        alphaSprite.style.transition = 'none';
      }, 600);
    });

    document.addEventListener('mouseleave', () => {
      if (isDragging) {
        isDragging = false;
        alphaSprite.style.cursor = 'grab';
        alphaSprite.style.transition = 'all 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)';
        alphaSprite.style.transform = 'translate(0, 0)';
        spriteCurrentX = 0;
        spriteCurrentY = 0;
        setTimeout(() => {
          alphaSprite.style.transition = 'none';
        }, 600);
      }
    });
  }

  // 鼠标靠近
  alphaSprite.addEventListener('mouseenter', () => {
    isNear = true;
    alphaSprite.classList.add('shy');
    alphaSprite.classList.add('attract');
    showBubble('near');
  });

  // 鼠标离开
  alphaSprite.addEventListener('mouseleave', () => {
    isNear = false;
    alphaSprite.classList.remove('shy');
    alphaSprite.classList.remove('attract');
    showBubble('far');
  });

  // 点击 - 幽灵跳跃 + 涟漪
  alphaSprite.addEventListener('click', (e) => {
    if (isDragging) return;
    
    const now = Date.now();
    const timeDiff = now - lastClickTime;

    if (timeDiff < 300) {
      // 双击 - 幽灵跳跃
      alphaSprite.classList.add('excited');
      showBubble('doubleClick');
      setTimeout(() => {
        alphaSprite.classList.remove('excited');
      }, 2000);
    } else {
      // 单击 - 幽灵跳跃
      alphaSprite.classList.add('excited');
      createRipple(e.clientX, e.clientY);
      showBubble('click');
      setTimeout(() => {
        alphaSprite.classList.remove('excited');
      }, 2000);
    }

    lastClickTime = now;
  });

  // 鼠标静止3秒 - 待机语
  function resetIdleTimer() {
    clearTimeout(idleTimeout);
    idleTimeout = setTimeout(() => {
      if (!isNear && !isDragging) {
        showBubble('idle');
      }
    }, 3000);
  }

  document.addEventListener('mousemove', resetIdleTimer);
  resetIdleTimer();

  // 页面滚动 - 滚动语
  let lastScrollY = 0;
  window.addEventListener('scroll', () => {
    const currentScrollY = window.scrollY;
    if (Math.abs(currentScrollY - lastScrollY) > 50) {
      showBubble('scroll');
      lastScrollY = currentScrollY;
    }
  });

  // 全局点击涟漪
  document.addEventListener('click', (e) => {
    if (!alphaSprite.contains(e.target)) {
      createRipple(e.clientX, e.clientY);
    }
  });

  // ============ Logo 拖拽摇晃效果 ============
  const logoSprite = document.getElementById('logo-sprite');
  let logoIsDragging = false;
  let logoStartX, logoStartY;
  let logoCurrentX = 0, logoCurrentY = 0;
  let logoVelocityX = 0, logoVelocityY = 0;
  let logoAnimating = false;

  if (logoSprite) {
    logoSprite.addEventListener('mousedown', (e) => {
      e.preventDefault();
      logoIsDragging = true;
      logoStartX = e.clientX - logoCurrentX;
      logoStartY = e.clientY - logoCurrentY;
      logoSprite.style.transition = 'none';
      logoAnimating = false;
    });

    document.addEventListener('mousemove', (e) => {
      if (!logoIsDragging) return;
      const newX = e.clientX - logoStartX;
      const newY = e.clientY - logoStartY;
      
      // 计算速度（用于惯性）
      logoVelocityX = newX - logoCurrentX;
      logoVelocityY = newY - logoCurrentY;
      
      logoCurrentX = newX;
      logoCurrentY = newY;
      
      // 应用摇晃旋转
      const rotationX = logoCurrentY * 0.5;
      const rotationY = -logoCurrentX * 0.5;
      logoSprite.style.transform = `translate(${logoCurrentX}px, ${logoCurrentY}px) rotateX(${rotationX}deg) rotateY(${rotationY}deg) scale(1.05)`;
    });

    document.addEventListener('mouseup', () => {
      if (!logoIsDragging) return;
      logoIsDragging = false;
      
      // 惯性动画
      logoAnimating = true;
      const startTime = Date.now();
      const startX = logoCurrentX, startY = logoCurrentY;
      const vx = logoVelocityX * 2, vy = logoVelocityY * 2;
      
      function animate() {
        if (!logoAnimating) return;
        
        const elapsed = Date.now() - startTime;
        const duration = 600;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 1 - Math.pow(1 - progress, 3);
        
        // 指数衰减
        const decay = Math.pow(0.9, elapsed / 16);
        logoCurrentX = startX + vx * decay;
        logoCurrentY = startY + vy * decay;
        
        // 回到原点
        logoCurrentX = logoCurrentX * (1 - ease);
        logoCurrentY = logoCurrentY * (1 - ease);
        
        const rotationX = logoCurrentY * 0.5;
        const rotationY = -logoCurrentX * 0.5;
        logoSprite.style.transform = `translate(${logoCurrentX}px, ${logoCurrentY}px) rotateX(${rotationX}deg) rotateY(${rotationY}deg)`;
        
        if (progress < 1) {
          requestAnimationFrame(animate);
        } else {
          logoSprite.style.transition = 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)';
          logoSprite.style.transform = 'translate(0, 0) rotateX(0) rotateY(0)';
          logoCurrentX = 0;
          logoCurrentY = 0;
          setTimeout(() => {
            logoSprite.style.transition = 'none';
          }, 400);
        }
      }
      
      animate();
    });
  }

  // ============ 在线演示系统 ============
  const demoInit = document.getElementById('demo-init');
  const demoGenerating = document.getElementById('demo-generating');
  const demoComplete = document.getElementById('demo-complete');
  const startDemoBtn = document.getElementById('start-demo-btn');
  const resetDemoBtn = document.getElementById('reset-demo-btn');
  const generateBtn = document.getElementById('generate-btn');
  const demoDid = document.getElementById('demo-did');
  const demoPubkey = document.getElementById('demo-pubkey');

  function generateRandomHex(length) {
    let result = '0x';
    const chars = '0123456789abcdef';
    for (let i = 0; i < length; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  }

  function generateDid() {
    const part1 = generateRandomHex(8).slice(2);
    const part2 = generateRandomHex(4).slice(2);
    const part3 = generateRandomHex(4).slice(2);
    const part4 = generateRandomHex(12).slice(2);
    return `did:aid:${part1}-${part2}-${part3}-${part4}`;
  }

  function startDemo() {
    demoInit.classList.add('hidden');
    demoGenerating.classList.remove('hidden');

    setTimeout(() => {
      demoGenerating.classList.add('hidden');
      demoComplete.classList.remove('hidden');

      // 生成随机 DID 和公钥
      demoDid.textContent = generateDid();
      demoPubkey.textContent = generateRandomHex(40);
    }, 2500);
  }

  function resetDemo() {
    demoComplete.classList.add('hidden');
    demoInit.classList.remove('hidden');
  }

  if (startDemoBtn) {
    startDemoBtn.addEventListener('click', startDemo);
  }

  if (generateBtn) {
    generateBtn.addEventListener('click', startDemo);
  }

  if (resetDemoBtn) {
    resetDemoBtn.addEventListener('click', resetDemo);
  }

  // ============ 注册/登录系统 ============
  var isLoggedIn = false;
  var currentUserDID = '';
  var regPhone = '';
  var regTimer = null;
  var regCountdown = 0;

  // ============ 平台配置 ============
  // 部署时修改这些值为实际的服务地址
  var CONFIG = {
    ds: 'http://localhost:3000',        // Ghost DS 操作台
    gateway: 'http://localhost:18080',  // Ghost Gateway
    nebula: 'http://localhost:2002',    // Nebula 工作流引擎
    orchestrator: 'http://localhost:19090', // Orchestrator
    alphaId: window.location.origin,    // Alpha-ID 服务（自动检测）
  };
  var GATEWAY_URL = CONFIG.gateway;

  window.showRegistration = function() {
    var modal = document.getElementById('reg-modal');
    if (!modal) return;
    resetRegistration();
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
    setTimeout(function() { var inp = document.getElementById('reg-phone'); if (inp) inp.focus(); }, 350);
  };

  window.closeRegistration = function() {
    var modal = document.getElementById('reg-modal');
    if (modal) modal.classList.remove('active');
    document.body.style.overflow = '';
    if (regTimer) { clearInterval(regTimer); regTimer = null; }
  };

  function resetRegistration() {
    document.querySelectorAll('.reg-step').forEach(function(s) { s.classList.remove('active'); });
    document.getElementById('reg-step-1').classList.add('active');
    for (var i = 1; i <= 4; i++) {
      var dot = document.getElementById('step-dot-' + i);
      if (dot) { dot.className = 'reg-step-dot'; if (i === 1) dot.classList.add('active'); }
    }
    document.querySelectorAll('.reg-error').forEach(function(e) { e.classList.remove('show'); e.textContent = ''; });
    var p = document.getElementById('reg-phone'); if (p) p.value = '';
    var s = document.getElementById('reg-sms-input'); if (s) s.value = '';
    var b = document.getElementById('reg-send-sms-btn');
    if (b) { b.disabled = false; b.textContent = '获取验证码'; }
    if (regTimer) { clearInterval(regTimer); regTimer = null; }
    regPhone = ''; regCountdown = 0;
    var st = document.getElementById('reg-sms-status'); if (st) st.textContent = '';
  }

  function goToStep(step) {
    document.querySelectorAll('.reg-step').forEach(function(s) { s.classList.remove('active'); });
    document.getElementById('reg-step-' + step).classList.add('active');
    for (var i = 1; i <= 4; i++) {
      var dot = document.getElementById('step-dot-' + i);
      if (dot) {
        dot.className = 'reg-step-dot';
        if (i < step) dot.classList.add('done');
        else if (i === step) dot.classList.add('active');
      }
    }
  }

  window.sendSMSCode = function() {
    var phone = document.getElementById('reg-phone').value.trim();
    var errorEl = document.getElementById('reg-phone-error');
    var sendBtn = document.getElementById('reg-send-sms-btn');
    var statusEl = document.getElementById('reg-sms-status');

    if (!/^1[3-9]\d{9}$/.test(phone)) {
      errorEl.textContent = '请输入正确的手机号';
      errorEl.classList.add('show');
      return;
    }
    errorEl.classList.remove('show');

    sendBtn.disabled = true;
    sendBtn.textContent = '发送中...';

    fetch(GATEWAY_URL + '/v1/register/send-sms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: phone })
    })
    .then(function(r) { return r.json(); })
    .then(function(resp) {
      regPhone = phone;
      if (resp.success && resp.data && resp.data.success) {
        if (resp.data.demo) {
          var si = document.getElementById('reg-sms-input');
          if (si) si.value = resp.data.demo;
          if (statusEl) statusEl.textContent = '演示模式：验证码已自动填入';
        }
        regCountdown = 60;
        sendBtn.textContent = '60s';
        regTimer = setInterval(function() {
          regCountdown--;
          sendBtn.textContent = regCountdown + 's';
          if (regCountdown <= 0) {
            clearInterval(regTimer); regTimer = null;
            sendBtn.disabled = false;
            sendBtn.textContent = '重新获取';
          }
        }, 1000);
      } else {
        sendBtn.disabled = false;
        sendBtn.textContent = '获取验证码';
        var errMsg = '发送失败，请重试';
        if (resp.data && resp.data.error) errMsg = resp.data.error;
        else if (resp.error) errMsg = resp.error;
        errorEl.textContent = errMsg;
        errorEl.classList.add('show');
      }
    })
    .catch(function(err) {
      sendBtn.disabled = false;
      sendBtn.textContent = '获取验证码';
      errorEl.textContent = '网络错误，请检查网关连接';
      errorEl.classList.add('show');
    });
  };

  window.verifySMS = function() {
    var code = document.getElementById('reg-sms-input').value.trim();
    var errorEl = document.getElementById('reg-phone-error');

    if (!code || code.length < 4) {
      errorEl.textContent = '请输入验证码';
      errorEl.classList.add('show');
      return;
    }
    errorEl.classList.remove('show');

    fetch(GATEWAY_URL + '/v1/register/verify-sms', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: regPhone, code: code })
    })
    .then(function(r) { return r.json(); })
    .then(function(resp) {
      if (resp.success && resp.data && resp.data.success) {
        document.getElementById('reg-step2-phone').textContent = regPhone + ' 已验证通过';
        goToStep(2);
      } else {
        var errMsg = '验证码错误';
        if (resp.data && resp.data.error) errMsg = resp.data.error;
        else if (resp.error) errMsg = resp.error;
        errorEl.textContent = errMsg;
        errorEl.classList.add('show');
      }
    })
    .catch(function(err) {
      errorEl.textContent = '网络错误，请检查网关连接';
      errorEl.classList.add('show');
    });
  };

  window.startFaceVerify = function() {
    var faceBtn = document.getElementById('reg-face-btn');
    var faceSkip = document.getElementById('reg-face-skip');
    var faceLoading = document.getElementById('reg-face-loading');
    var faceError = document.getElementById('reg-face-error');

    faceBtn.style.display = 'none';
    faceSkip.style.display = 'none';
    faceLoading.style.display = 'block';
    faceError.classList.remove('show');

    goToStep(3);

    fetch(GATEWAY_URL + '/v1/register/face-verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: regPhone })
    })
    .then(function(r) { return r.json(); })
    .then(function(resp) {
      faceLoading.style.display = 'none';
      if (resp.success && resp.data && resp.data.realName) {
        generateAndCompleteDID();
      } else if (resp.success && resp.data && resp.data.passed) {
        generateAndCompleteDID();
      } else if (resp.success && resp.data && resp.data.certifyUrl) {
        faceBtn.style.display = 'flex';
        faceSkip.style.display = 'block';
        window.open(resp.data.certifyUrl, '_blank');
      } else {
        faceBtn.style.display = 'flex';
        faceSkip.style.display = 'block';
        var errMsg = '请求失败';
        if (resp.data && resp.data.error) errMsg = resp.data.error;
        else if (resp.error) errMsg = resp.error;
        faceError.textContent = errMsg;
        faceError.classList.add('show');
      }
    })
    .catch(function(err) {
      faceLoading.style.display = 'none';
      faceBtn.style.display = 'flex';
      faceSkip.style.display = 'block';
      faceError.textContent = '网络错误，请检查网关连接';
      faceError.classList.add('show');
    });
  };

  window.skipFaceVerify = function() {
    generateAndCompleteDID();
  };

  function generateAndCompleteDID() {
    if (regTimer) { clearInterval(regTimer); regTimer = null; }

    fetch(GATEWAY_URL + '/v1/register/generate-did', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: regPhone })
    })
    .then(function(r) { return r.json(); })
    .then(function(resp) {
      if (resp.success && resp.data && resp.data.did) {
        currentUserDID = resp.data.did;
        document.getElementById('reg-did-result').textContent = resp.data.did;
        goToStep(4);
        return fetch(GATEWAY_URL + '/v1/register/complete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ did: resp.data.did, phone: regPhone })
        });
      } else {
        currentUserDID = 'did:aid:fallback-' + Date.now().toString(36);
        document.getElementById('reg-did-result').textContent = currentUserDID;
        goToStep(4);
      }
    })
    .catch(function(err) {
      currentUserDID = 'did:aid:offline-' + Date.now().toString(36);
      document.getElementById('reg-did-result').textContent = currentUserDID + ' (离线模式)';
      goToStep(4);
    });
  }

  window.finishRegistration = function() {
    closeRegistration();
    isLoggedIn = true;

    var loginBtn = document.getElementById('header-login-btn');
    var profileBtn = document.getElementById('profile-btn');
    if (loginBtn) loginBtn.classList.add('hidden');
    if (profileBtn) profileBtn.classList.remove('hidden');

    var didDisplay = document.getElementById('user-did-display');
    if (didDisplay) didDisplay.textContent = currentUserDID.substring(0, 20) + '…';

    var settingsDid = document.getElementById('settings-did');
    if (settingsDid) settingsDid.textContent = currentUserDID;

    showWorkbench();
    // 注册后引导：加载控制台数据
    setTimeout(function() {
      loadDashboard();
    }, 500);
  };
  // ============ 视图切换 ============
  window.showHomepage = function() {
    document.getElementById('workbenchView').classList.remove('active');
    document.getElementById('mindflowView').classList.remove('active');
    document.getElementById('homepageView').classList.add('active');
  };

  window.showMindflow = function() {
    document.getElementById('homepageView').classList.remove('active');
    document.getElementById('workbenchView').classList.remove('active');
    document.getElementById('mindflowView').classList.add('active');
    window.scrollTo(0, 0);
  };

  // ============ 导航处理 ============
  window.navigateToSection = function(sectionId) {
    // 如果已登录且点击的是 Web 4.0 相关
    if (isLoggedIn && sectionId === 'architecture') {
      showWorkbench();
      return;
    }
    showHomepage();
    setTimeout(function() {
      var el = document.getElementById(sectionId);
      if (el) el.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  // 为导航链接添加点击处理
  document.querySelectorAll('.nav-pill').forEach(function(link) {
    link.addEventListener('click', function(e) {
      var href = this.getAttribute('href');
      if (href && href.startsWith('#')) {
        e.preventDefault();
        var sectionId = href.substring(1);
        navigateToSection(sectionId);
      }
    });
  });

  // ============ A2A 生态区视图 ============
  window.showA2AView = function() {
    document.getElementById('homepageView').classList.remove('active');
    document.getElementById('mindflowView').classList.remove('active');
    var a2aView = document.getElementById('workbenchView');
    if (a2aView) a2aView.classList.add('active');
    window.scrollTo(0, 0);
    // 默认加载控制台数据
    loadDashboard();
  };
  // 兼容旧名称
  window.showWorkbench = window.showA2AView;

  // ============ 三层平台导航 ============
  window.showLayer = function(sectionId) {
    // 确保 homepageView 为活跃视图
    document.getElementById('homepageView').classList.add('active');
    document.getElementById('mindflowView').classList.remove('active');
    document.getElementById('workbenchView').classList.remove('active');
    // 滚动到目标区域
    var target = document.getElementById(sectionId);
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };
  // 兼容旧名称
  window.showHomepage = window.showLayer;

  // ============ 控制台数据加载 ============
  
  function loadDashboard() {
    loadAgentStatus();
    loadAuditLogs();
    loadMemoryStats();
  }
  
  function loadAgentStatus() {
    var dashTotalAgents = document.getElementById('dash-total-agents');
    var dashTotalSkills = document.getElementById('dash-total-skills');
    var dashAuditCount = document.getElementById('dash-audit-count');
    var dashSystemHealth = document.getElementById('dash-system-health');
    var dashPrivateList = document.getElementById('dash-private-list');
    var dashPrivateCount = document.getElementById('dash-private-count');
    
    fetch(GATEWAY_URL + '/v1/agent/a2a/agents')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var agents = data.agents || [];
        if (dashTotalAgents) dashTotalAgents.textContent = agents.length;
        if (dashPrivateCount) dashPrivateCount.textContent = agents.length + ' 个';
        if (dashPrivateList) {
          if (agents.length === 0) {
            dashPrivateList.innerHTML = '<div class="text-xs text-slate-500 py-2">暂无 Agent，注册后自动出现</div>';
          } else {
            dashPrivateList.innerHTML = agents.map(function(a) {
              return '<div class="flex items-center gap-2 py-1">' +
                '<span class="w-2 h-2 rounded-full bg-emerald-400"></span>' +
                '<span class="text-sm text-white font-mono">' + (a.did || a.agent_id || 'unknown') + '</span>' +
                '<span class="text-[10px] text-slate-400 ml-auto">' + (a.skills || []).length + ' skills</span></div>';
            }).join('');
          }
        }
      })
      .catch(function() {
        if (dashTotalAgents) dashTotalAgents.textContent = '!';
      });
    
    fetch(GATEWAY_URL + '/v1/agent/a2a/skills')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (dashTotalSkills) dashTotalSkills.textContent = data.length || 0;
      })
      .catch(function() {
        if (dashTotalSkills) dashTotalSkills.textContent = '!';
      });
    
    fetch(GATEWAY_URL + '/health')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (dashSystemHealth) dashSystemHealth.textContent = data.status === 'ok' ? 'OK' : 'WARN';
        if (dashSystemHealth) dashSystemHealth.className = 'text-2xl font-black ' + (data.status === 'ok' ? 'text-emerald-300' : 'text-amber-300');
      })
      .catch(function() {
        if (dashSystemHealth) dashSystemHealth.textContent = '!';
      });
  }
  
  function loadAuditLogs() {
    var execLogs = document.getElementById('exec-logs');
    if (!execLogs) return;
    
    fetch(GATEWAY_URL + '/v1/agent/a2a/audit?limit=20')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.records && data.records.length > 0) {
          execLogs.innerHTML = data.records.map(function(r) {
            var time = new Date(r.timestamp || Date.now()).toLocaleTimeString();
            var statusColor = r.success ? 'text-emerald-400' : 'text-red-400';
            var icon = r.success ? '✓' : '✗';
            return '<div class="flex items-start gap-2 py-1.5 border-b border-white/5 last:border-0">' +
              '<span class="text-[10px] text-slate-500 font-mono whitespace-nowrap">' + time + '</span>' +
              '<span class="text-xs ' + statusColor + '">' + icon + ' ' + (r.event || 'call') + '</span>' +
              '<span class="text-xs text-slate-300">' + (r.skill || r.caller_agent_id || '') + '</span></div>';
          }).join('');
        } else {
          execLogs.innerHTML = '<div class="text-center text-slate-500 py-4">暂无审计记录</div>';
        }
      })
      .catch(function() {
        execLogs.innerHTML = '<div class="text-center text-red-400 py-4">加载失败</div>';
      });
  }
  
  function loadMemoryStats() {
    var memTotal = document.getElementById('mem-total');
    var memPrivate = document.getElementById('mem-private');
    var memKnowledge = document.getElementById('mem-knowledge');
    if (!memTotal) return;
    
    fetch(GATEWAY_URL + '/v1/dual-chain/stats')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (memTotal) memTotal.textContent = data.total || data.count || '-';
        if (memPrivate) memPrivate.textContent = data.private_count || '-';
        if (memKnowledge) memKnowledge.textContent = data.knowledge_count || '-';
      })
      .catch(function() {
        if (memTotal) memTotal.textContent = '-';
      });
  }
  
  // ============ A2A 网络拓扑图（D3.js 力导向图） ============
  
  function renderTopology() {
    var svg = document.getElementById('topology-svg');
    if (!svg) return;
    
    fetch(GATEWAY_URL + '/v1/agent/a2a/agents')
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var agents = data.agents || [];
        var statsEl = document.getElementById('topology-stats');
        if (statsEl) statsEl.textContent = agents.length + ' 个节点';
        
        if (agents.length === 0) {
          svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="#64748b" font-size="14">暂无 Agent 数据</text>';
          return;
        }
        
        // D3 力导向图
        var width = svg.clientWidth || 800;
        var height = svg.clientHeight || 500;
        
        var nodes = agents.map(function(a, i) {
          return {
            id: a.did || a.agent_id || 'agent-' + i,
            label: (a.did || a.agent_id || 'unknown').substring(0, 20),
            skills: (a.skills || []).length,
            status: a.status || 'online',
            group: a.endpoint ? 1 : 0,
          };
        });
        
        // 构造连线（同 endpoint 域名的 Agent 互连）
        var links = [];
        var groups = {};
        nodes.forEach(function(n) {
          var g = n.group.toString();
          if (!groups[g]) groups[g] = [];
          groups[g].push(n.id);
        });
        Object.values(groups).forEach(function(members) {
          for (var i = 0; i < members.length - 1; i++) {
            links.push({ source: members[i], target: members[i + 1] });
          }
        });
        
        var simulation = d3.forceSimulation(nodes)
          .force('link', d3.forceLink(links).id(function(d) { return d.id; }).distance(120))
          .force('charge', d3.forceManyBody().strength(-300))
          .force('center', d3.forceCenter(width / 2, height / 2))
          .force('collision', d3.forceCollide().radius(40));
        
        var g = d3.select(svg).selectAll('*').remove();
        var link = g.append('g').selectAll('line')
          .data(links).join('line')
          .attr('stroke', 'rgba(139,92,246,0.2)')
          .attr('stroke-width', 1.5);
        
        var node = g.append('g').selectAll('circle')
          .data(nodes).join('circle')
          .attr('r', function(d) { return 8 + (d.skills || 0) * 2; })
          .attr('fill', function(d) { return d.status === 'online' ? '#34d399' : '#94a3b8'; })
          .attr('stroke', function(d) { return d.status === 'online' ? '#6ee7b7' : '#cbd5e1'; })
          .attr('stroke-width', 2)
          .style('cursor', 'pointer')
          .call(d3.drag()
            .on('start', function(event, d) { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
            .on('drag', function(event, d) { d.fx = event.x; d.fy = event.y; })
            .on('end', function(event, d) { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }));
        
        var label = g.append('g').selectAll('text')
          .data(nodes).join('text')
          .text(function(d) { return d.label; })
          .attr('font-size', 9).attr('fill', '#94a3b8').attr('dx', 12).attr('dy', 3);
        
        simulation.on('tick', function() {
          link.attr('x1', function(d) { return d.source.x; }).attr('y1', function(d) { return d.source.y; })
              .attr('x2', function(d) { return d.target.x; }).attr('y2', function(d) { return d.target.y; });
          node.attr('cx', function(d) { return d.x; }).attr('cy', function(d) { return d.y; });
          label.attr('x', function(d) { return d.x; }).attr('y', function(d) { return d.y; });
        });
        
        node.on('click', function(event, d) {
          var detail = document.getElementById('topology-detail');
          detail.classList.remove('hidden');
          document.getElementById('topology-detail-title').textContent = d.label;
          document.getElementById('topology-detail-content').textContent = '状态: ' + d.status + ' | Skills: ' + d.skills;
          document.getElementById('topology-detail-meta').textContent = 'ID: ' + d.id;
        });
      })
      .catch(function() {
        svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="#ef4444" font-size="14">加载失败</text>';
      });
  }
  
  // 拓扑图按钮绑定
  var topologyBtn = document.querySelector('[data-route="a2a-network"]');
  if (topologyBtn) {
    topologyBtn.addEventListener('click', function() {
      setTimeout(renderTopology, 200);
    });
  }
  
  // ============ Mindflow Tab 切换 ============
  window.switchMindflowTab = function(tab) {
    ['canvas', 'tasks', 'notes', 'profile'].forEach(function(t) {
      var panel = document.getElementById('mf-' + t + '-panel');
      if (panel) panel.classList.add('hidden');
    });
    var target = document.getElementById('mf-' + tab + '-panel');
    if (target) target.classList.remove('hidden');
  };
  
  // 切换到工作台时加载统计数据
  window.showWorkbench = function() {
    document.getElementById('homepageView').classList.remove('active');
    document.getElementById('mindflowView').classList.remove('active');
    document.getElementById('workbenchView').classList.add('active');
    window.scrollTo(0, 0);
    // 动态设置 iframe 地址
    var iframe = document.getElementById('doubao-iframe-src');
    if (iframe && !iframe.src) {
      iframe.src = CONFIG.gateway + '/v1/doubao';
    }
    setTimeout(loadDashboard, 100);
  };

  // ============ 💬 豆包记忆桥 ============
  window.loadDoubao = function() {
    updateStatus();
    updateConvList();
  };
  
    window.updateStatus = function() {
    // Gateway health
    fetch(CONFIG.gateway + '/health').then(function(r){return r.json()}).then(function(h){
      if (h.success) {
        var gwOk = h.data && h.data.gateway === 'ok';
        document.getElementById('doubao-status').innerHTML = gwOk ? '🟢 连接正常' : '🟡 部分异常';
      }
    }).catch(function(){
      document.getElementById('doubao-status').innerHTML = '🔴 Gateway 未连';
    });

    // Nebula (Feishu bot) health - check via orchestrator
    fetch(CONFIG.orchestrator + '/health').then(function(r){return r.json()}).then(function(d){
      document.getElementById('doubao-nebula').innerHTML = '🟢 连接中';
    }).catch(function(){
      document.getElementById('doubao-nebula').innerHTML = '🟡 Orchestrator 未启动';
    });
    
    // Obsidian vault - check directory exists with recent files
    var obsEl = document.getElementById('doubao-obsidian');
    // Can't check local filesystem from browser, but we can check via gateway
    fetch(CONFIG.gateway + '/health').then(function(r){return r.json()}).then(function(h){
      var hasObsidian = h.data && h.data.obsidian === 'ok';
      obsEl.innerHTML = hasObsidian ? '📄 已关联' : '📄 未连接';
    }).catch(function(){
      obsEl.innerHTML = '📄 等待中';
    });
    
    document.getElementById('doubao-refresh-time').textContent = new Date().toLocaleTimeString();
  };  window.updateConvList = function() {
    var list = document.getElementById('doubao-conv-list');
    if (!list) return;
    list.innerHTML = '<div class="text-center text-slate-500 py-8 text-sm">加载中...</div>';
    
    // Direct Obsidian vault search - zero token cost
    fetch(CONFIG.gateway + '/v1/memory/search?limit=10')
    .then(function(r){return r.json()})
    .then(function(res){
      if (res.success && res.data && res.data.results && res.data.results.length > 0) {
        var html = '';
        res.data.results.forEach(function(mem) {
          var dateStr = mem.date || '未知';
          var preview = (mem.preview || '').substring(0, 150);
          preview = preview.replace(/</g, '&lt;').replace(/>/g, '&gt;');
          var tags = (mem.tags || []).map(function(t){
            return '<span class="inline-block text-xs px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-400">' + t + '</span>';
          }).join(' ');
          html += '<div class="conv-item p-3 rounded-lg bg-white/5 border border-white/10 mb-2 hover:bg-white/10 transition">';
          html += '<div class="text-xs text-slate-500 mb-1">' + dateStr + ' · ' + (mem.category || '') + '</div>';
          html += '<div class="text-sm text-slate-300 line-clamp-3">' + preview + '</div>';
          if (tags) html += '<div class="mt-1 flex gap-1 flex-wrap">' + tags + '</div>';
          html += '</div>';
        });
        list.innerHTML = html;
      } else {
        list.innerHTML = '<div class="text-center text-slate-500 py-8 text-sm">暂无同步记忆</div>';
      }
    }).catch(function(err){
      list.innerHTML = '<div class="text-center text-slate-500 py-8 text-sm">请确保 Gateway 已启动 (port 18080)</div>';
    });
  };
  
  window.searchDoubao = function() {
    var q = document.getElementById('doubao-search-input').value.trim();
    if (!q) { updateConvList(); return; }
    var list = document.getElementById('doubao-conv-list');
    if (!list) return;
    list.innerHTML = '<div class="text-center text-slate-500 py-8 text-sm">搜索中...</div>';
    
    // Search via Obsidian vault (zero token cost)
    fetch(CONFIG.gateway + '/v1/memory/search?keyword=' + encodeURIComponent(q) + '&limit=20')
    .then(function(r){return r.json()})
    .then(function(res){
      if (res.success && res.data && res.data.results && res.data.results.length > 0) {
        var html = '<div class="text-xs text-slate-500 mb-3">找到 ' + res.data.total + ' 条结果</div>';
        res.data.results.forEach(function(mem) {
          var dateStr = mem.date || '未知';
          var preview = (mem.preview || '').substring(0, 200);
          preview = preview.replace(/</g, '&lt;').replace(/>/g, '&gt;');
          // Highlight keyword
          var re = new RegExp('(' + q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi');
          preview = preview.replace(re, '<mark class="bg-sky-500/30 text-sky-200 px-0.5 rounded">$1</mark>');
          html += '<div class="conv-item p-3 rounded-lg bg-white/5 border border-white/10 mb-2">';
          html += '<div class="text-xs text-slate-500 mb-1">' + dateStr + ' · ' + mem.category + '</div>';
          html += '<div class="text-sm text-slate-300">' + preview + '</div>';
          html += '</div>';
        });
        list.innerHTML = html;
      } else {
        list.innerHTML = '<div class="text-center text-slate-500 py-8 text-sm">未找到相关记忆</div>';
      }
    }).catch(function(){
      list.innerHTML = '<div class="text-center text-slate-500 py-8 text-sm">搜索失败，请确保 Gateway 已启动</div>';
    });
  };
  
// ============ 🌌 记忆星云 ============
  window.loadGraph = function() {
    var svg = document.getElementById('graph-svg');
    if (!svg) return;
    
    // Load d3.js if not loaded
    if (typeof d3 === 'undefined') {
      var script = document.createElement('script');
      script.src = 'https://d3js.org/d3.v7.min.js';
      script.onload = function() { renderGraph(); };
      document.head.appendChild(script);
    } else {
      renderGraph();
    }
  };
  
  function renderGraph() {
    fetch(CONFIG.gateway + '/v1/memory/graph').then(function(r){return r.json()}).then(function(resp){
      if (!resp.success || !resp.data) return;
      var data = resp.data;
      document.getElementById('graph-stats').textContent = data.nodes.length + ' 节点·' + data.edges.length + ' 连线';
      
      var svg = d3.select('#graph-svg');
      svg.selectAll('*').remove();
      
      var width = svg.node().parentElement.clientWidth || 800;
      var height = 480;
      svg.attr('viewBox', [0, 0, width, height]);
      
      var simulation = d3.forceSimulation(data.nodes)
        .force('link', d3.forceLink(data.edges).id(function(d){return d.id;}).distance(80))
        .force('charge', d3.forceManyBody().strength(-200))
        .force('center', d3.forceCenter(width/2, height/2))
        .force('collision', d3.forceCollide().radius(30));
      
      var g = svg.append('g');
      
      var link = g.append('g').selectAll('line').data(data.edges).join('line')
        .attr('stroke', '#334155').attr('stroke-width', 1).attr('stroke-opacity', 0.4);
      
      var node = g.append('g').selectAll('circle').data(data.nodes).join('circle')
        .attr('r', 8).attr('fill', function(d){return d.color || '#64748b';})
        .attr('stroke', '#1e293b').attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('click', function(e, d){ showNodeDetail(d); })
        .call(d3.drag()
          .on('start', function(e,d){if(!e.active)simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y;})
          .on('drag', function(e,d){d.fx=e.x; d.fy=e.y;})
          .on('end', function(e,d){if(!e.active)simulation.alphaTarget(0); d.fx=null; d.fy=null;}));
      
      var label = g.append('g').selectAll('text').data(data.nodes).join('text')
        .text(function(d){return d.label.substring(0,12);})
        .attr('font-size', 8).attr('fill', '#94a3b8').attr('dx', 12).attr('dy', 3);
      
      simulation.on('tick', function() {
        link.attr('x1', function(d){return d.source.x;}).attr('y1', function(d){return d.source.y;})
            .attr('x2', function(d){return d.target.x;}).attr('y2', function(d){return d.target.y;});
        node.attr('cx', function(d){return d.x;}).attr('cy', function(d){return d.y;});
        label.attr('x', function(d){return d.x;}).attr('y', function(d){return d.y;});
      });
    });
  }
  
  function showNodeDetail(d) {
    var detail = document.getElementById('graph-detail');
    detail.classList.remove('hidden');
    document.getElementById('graph-detail-title').textContent = d.label;
    document.getElementById('graph-detail-content').textContent = d.source + ' | ' + d.category;
    document.getElementById('graph-detail-meta').textContent = '标签: ' + (d.tags || []).join(', ') + ' | 颜色: ' + d.color;
  }
  
  var graphBtn = document.querySelector('[data-route="graph"]');
  if (graphBtn) {
    graphBtn.addEventListener('click', function() {
      setTimeout(loadGraph, 200);
    });
  }
  
  // Auto-load agents on workbench entry if already logged in
  var authToken = localStorage.getItem('aid_access_token') || localStorage.getItem('access_token');
  if (authToken) {
    // Pre-fetch agent status when workbench is active
    var workbenchObserver = new MutationObserver(function(mutations) {
      mutations.forEach(function(m) {
        if (m.target.id === 'workbenchView' && m.target.classList.contains('active')) {
          loadAgentStatus();
          loadAuditLogs();
        }
      });
    });
    var wbView = document.getElementById('workbenchView');
    if (wbView) {
      workbenchObserver.observe(wbView, { attributes: true, attributeFilter: ['class'] });
    }
  }
  
});
