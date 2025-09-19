(function () {
  function onReady(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  function initOnce() {
    var pinInput = document.getElementById('fk-pin');
    var keypad   = document.getElementById('fk-keypad');
    var eyeBtn   = document.querySelector('.fk-eye');
    var form     = document.getElementById('fk-form');

    if (!pinInput) return; // chờ đến khi form render xong

    // Autofocus
    try { pinInput.focus(); } catch (e) {}

    // Loading state cho form submit
    if (form) {
      form.addEventListener('submit', function(e) {
        var submitBtn = form.querySelector('.fk-submit');
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Đang xử lý...';
        }
      });
    }

    // Toggle hiện/ẩn PIN
    if (eyeBtn) {
      eyeBtn.addEventListener('click', function (ev) {
        ev.preventDefault();
        pinInput.type = (pinInput.type === 'password') ? 'text' : 'password';
        pinInput.focus();
      });
    }

    // Bắt sự kiện click trên keypad (robust với closest)
    if (keypad) {
      keypad.addEventListener('click', function (e) {
        var btn = e.target.closest('.fk-key');
        if (!btn || !keypad.contains(btn)) return;
        e.preventDefault();

        // Visual feedback
        btn.style.transform = 'scale(0.95)';
        setTimeout(() => btn.style.transform = '', 100);

        var key = btn.getAttribute('data-key');
        if (!key) return;

        if (key === 'del') {
          pinInput.value = pinInput.value.slice(0, -1);
        } else if (key === 'clr') {
          pinInput.value = '';
        } else if (/^[0-9]$/.test(key)) {
          if (pinInput.value.length < 6) { // Giới hạn 6 số
            pinInput.value += key;
          }
        }
        pinInput.focus();
        
        // Pulse effect khi nhập
        if (/^[0-9]$/.test(key) && pinInput.value.length <= 6) {
          pinInput.style.borderColor = '#4f89f4';
          setTimeout(() => pinInput.style.borderColor = '', 200);
        }
      });
    }

    // Bắt phím cứng từ bàn phím: 0-9, Backspace, Delete
    document.addEventListener('keydown', function (e) {
      if (!pinInput) return;
      var k = e.key;

      if (/^[0-9]$/.test(k)) {
        if (pinInput.value.length < 6) { // Giới hạn 6 số
          pinInput.value += k;
          // Visual feedback
          pinInput.style.borderColor = '#4f89f4';
          setTimeout(() => pinInput.style.borderColor = '', 200);
        }
        e.preventDefault();
      } else if (k === 'Backspace') {
        pinInput.value = pinInput.value.slice(0, -1);
        e.preventDefault();
      } else if (k === 'Delete') {
        pinInput.value = '';
        e.preventDefault();
      }
    }, { capture: true });
  }

  // Khởi tạo khi DOM sẵn sàng
  onReady(function () {
    // Nếu phần tử chưa có (do render QWeb trễ), dùng MutationObserver để chờ
    if (document.getElementById('fk-pin')) {
      initOnce();
      return;
    }
    var mo = new MutationObserver(function () {
      if (document.getElementById('fk-pin')) {
        mo.disconnect();
        initOnce();
      }
    });
    mo.observe(document.documentElement, { childList: true, subtree: true });
  });
})();
