(function(){
  var toggle = document.getElementById('sidebarToggle');
  var sidebar = document.getElementById('sidebar');
  var overlay = null;

  function createOverlay(){
    overlay = document.createElement('div');
    overlay.className = 'overlay';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', close);
  }

  function open(){
    if(!sidebar) return;
    sidebar.classList.add('open');
    if(!overlay) createOverlay();
    overlay.classList.add('show');
    document.body.style.overflow = 'hidden';
  }
  function close(){
    if(!sidebar) return;
    sidebar.classList.remove('open');
    if(overlay) overlay.classList.remove('show');
    document.body.style.overflow = '';
  }

  function toggleHandler(e){
    if(!sidebar) return;
    if(sidebar.classList.contains('open')) close(); else open();
  }

  if(toggle){
    toggle.addEventListener('click', toggleHandler);
  }

  // Закрыть по Esc
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape') close();
  });
})();
