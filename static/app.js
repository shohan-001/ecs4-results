// ===== UoK Multi-Department Results Portal =====
var currentDept = '';
var DATA = [];
var sortMode = 'default';
var filterMode = 'all';
var expanded = {};
var adminToken = '';

var DEPTS = {
  ec: {name:'Electronics & Computer Science', icon:'💻', color:'#1a73e8'},
  ps: {name:'Physical Science', icon:'🔬', color:'#7b1fa2'},
  pe: {name:'Physics & Electronics', icon:'⚡', color:'#f57c00'},
  ss: {name:'Sport Science', icon:'🏅', color:'#2e7d32'},
  bs: {name:'Biological Science', icon:'🧬', color:'#00897b'},
  ac: {name:'Applied Chemistry', icon:'⚗️', color:'#c62828'},
  em: {name:'Environmental Management', icon:'🌿', color:'#558b2f'},
  se: {name:'Software Engineering', icon:'🖥️', color:'#0277bd'}
};

var GRADE_PTS = {'A+':4,'A':4,'A-':3.7,'B+':3.3,'B':3,'B-':2.7,'C+':2.3,'C':2,'C-':1.7,'D+':1.3,'D':1,'E':0,'F':0,'**':0};

// ===== LOGIN =====
function togglePassword() {
  var p = document.getElementById('loginPwd');
  p.type = p.type === 'password' ? 'text' : 'password';
}

function handleLogin(e) {
  e.preventDefault();
  var u = document.getElementById('loginUser').value.trim();
  var p = document.getElementById('loginPwd').value;
  var err = document.getElementById('loginError');
  if (!u || !p) { err.textContent = 'Enter username and password'; return; }
  fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:u, password:p})})
    .then(r => r.json()).then(d => {
      if (d.ok) { localStorage.setItem('uok_user', u); err.textContent = ''; showDeptPage(); }
      else { err.textContent = d.error || 'Invalid credentials'; }
    }).catch(() => { err.textContent = 'Connection error'; });
}

function handleLogout() {
  localStorage.removeItem('uok_user');
  adminToken = '';
  document.getElementById('loginPage').classList.remove('hidden');
  document.getElementById('deptPage').classList.add('hidden');
  document.getElementById('resultsPage').classList.add('hidden');
  document.getElementById('adminPage').classList.add('hidden');
}

// ===== DEPARTMENT PAGE =====
function showDeptPage() {
  document.getElementById('loginPage').classList.add('hidden');
  document.getElementById('resultsPage').classList.add('hidden');
  document.getElementById('adminPage').classList.add('hidden');
  document.getElementById('deptPage').classList.remove('hidden');
  renderDeptGrid();
  fetch('/data/scrape_state.json?v='+Date.now()).then(r=>r.json()).then(s=>{
    if(s.last_rotation) document.getElementById('lastUpdated').textContent = s.last_rotation;
  }).catch(()=>{});
}

function renderDeptGrid() {
  var html = '';
  Object.keys(DEPTS).forEach(code => {
    var d = DEPTS[code];
    html += '<div class="dept-card" onclick="openDept(\'' + code + '\')">';
    html += '<div class="dept-icon" style="background:' + d.color + '22;color:' + d.color + '">' + d.icon + '</div>';
    html += '<div class="dept-card-info"><h3>' + d.name + '</h3><p>' + code.toUpperCase() + '/2023</p>';
    html += '<div class="dept-count" id="count_' + code + '">Loading...</div></div></div>';
  });
  document.getElementById('deptGrid').innerHTML = html;
  // Load counts
  Object.keys(DEPTS).forEach(code => {
    fetch('/data/' + code + '/results.json?v=' + Date.now()).then(r => {
      if (!r.ok) throw 0; return r.json();
    }).then(data => {
      var s = data.filter(r => !r.error).length;
      var p = data.filter(r => r.error).length;
      document.getElementById('count_' + code).textContent = s + ' results' + (p ? ', ' + p + ' protected' : '');
    }).catch(() => {
      document.getElementById('count_' + code).textContent = 'Not discovered yet';
    });
  });
}

// ===== RESULTS VIEW =====
function openDept(code) {
  currentDept = code;
  var d = DEPTS[code];
  document.getElementById('deptTitle').textContent = d.name;
  document.getElementById('deptSubtitle').textContent = code.toUpperCase() + '/2023 — Faculty of Science';
  document.getElementById('deptPage').classList.add('hidden');
  document.getElementById('resultsPage').classList.remove('hidden');
  document.getElementById('studentList').innerHTML = '<div style="text-align:center;padding:40px;color:#999">Loading results...</div>';
  
  sortMode = 'default'; filterMode = 'all'; expanded = {};
  document.getElementById('sortBtn').textContent = 'Sort';
  document.getElementById('sortBtn').className = 'sort-btn';
  document.getElementById('searchInput').value = '';
  document.querySelectorAll('.tab-row .tab').forEach((t,i) => t.className = 'tab' + (i===0?' active':''));

  fetch('/data/' + code + '/results.json?v=' + Date.now()).then(r => {
    if (!r.ok) throw 0; return r.json();
  }).then(data => {
    DATA = processData(data);
    renderSummary();
    renderResults();
  }).catch(() => {
    document.getElementById('studentList').innerHTML = '<div style="text-align:center;padding:40px;color:#999">No data yet. Run discovery from Admin panel.</div>';
    document.getElementById('summaryBar').innerHTML = '';
  });
}

function goBack() {
  document.getElementById('resultsPage').classList.add('hidden');
  showDeptPage();
}

function processData(raw) {
  return raw.map(s => {
    s.isProtected = s.error === 'protected' || s.error === 'no_year1';
    s.isSuccess = !s.error;
    if (s.isSuccess) s.actual_gpa = calcGPA(s.courses);
    return s;
  });
}

function calcGPA(courses) {
  if (!courses) return null;
  var tp = 0, tc = 0;
  courses.forEach(c => {
    var code = c['Course Code'] || '';
    var grade = (c['Grade'] || '').trim();
    if (code.startsWith('Course Code') || code.startsWith('ACLT') || !grade) return;
    var cr = parseInt(code.slice(-1)) || 0;
    if (!cr) return;
    var pts = GRADE_PTS[grade.toUpperCase()];
    if (pts === undefined) return;
    tp += pts * cr; tc += cr;
  });
  return tc > 0 ? (tp / tc).toFixed(2) : null;
}

function renderSummary() {
  var total = DATA.length;
  var success = DATA.filter(s => s.isSuccess).length;
  var prot = DATA.filter(s => s.isProtected).length;
  var gpas = DATA.filter(s => s.actual_gpa).map(s => parseFloat(s.actual_gpa));
  var avg = gpas.length ? (gpas.reduce((a,b) => a+b, 0) / gpas.length).toFixed(2) : '—';
  document.getElementById('summaryBar').innerHTML =
    '<div class="summary-card"><div class="num blue">' + total + '</div><div class="label">Total</div></div>' +
    '<div class="summary-card"><div class="num green">' + success + '</div><div class="label">Results</div></div>' +
    '<div class="summary-card"><div class="num orange">' + prot + '</div><div class="label">Protected</div></div>' +
    '<div class="summary-card"><div class="num blue">' + avg + '</div><div class="label">Avg GPA</div></div>';
}

function gradeClass(g) {
  if (!g) return '';
  var u = g.trim().toUpperCase();
  if (u.startsWith('A')) return 'grade-a'; if (u.startsWith('B')) return 'grade-b';
  if (u.startsWith('C')) return 'grade-c'; if (u.startsWith('D')) return 'grade-d';
  if (u==='**'||u==='E'||u==='F') return 'grade-fail'; return '';
}
function gpaClass(g) { var v=parseFloat(g); if(isNaN(v))return''; return v>=2.5?'gpa-high':v>=1.5?'gpa-mid':'gpa-low'; }
function toggleDetails(id) { expanded[id] = !expanded[id]; renderResults(); }

function toggleSort() {
  var m=['default','gpa-desc','gpa-asc','name'], l=['Sort','GPA ↓','GPA ↑','Name'];
  var i = (m.indexOf(sortMode)+1) % m.length;
  sortMode = m[i];
  document.getElementById('sortBtn').textContent = l[i];
  document.getElementById('sortBtn').className = sortMode==='default'?'sort-btn':'sort-btn active';
  renderResults();
}

function setTab(mode) {
  filterMode = mode;
  document.querySelectorAll('.tab-row .tab').forEach(t => t.className = 'tab' + (t.textContent.toLowerCase().startsWith(mode.substring(0,3)) ? ' active' : ''));
  renderResults();
}

function renderResults() {
  var q = document.getElementById('searchInput').value.toLowerCase();
  var filtered = DATA.filter(s => {
    if (filterMode==='results' && !s.isSuccess) return false;
    if (filterMode==='protected' && !s.isProtected) return false;
    if (!q) return true;
    var t = (s.student_id+' '+(s.name_initial||'')+' '+(s.full_name||'')).toLowerCase();
    if (t.indexOf(q)>=0) return true;
    return (s.courses||[]).some(c => ((c['Course Code']||'')).toLowerCase().indexOf(q)>=0);
  });

  if (sortMode==='gpa-desc') filtered.sort((a,b) => (parseFloat(b.actual_gpa||b.gpa)||0) - (parseFloat(a.actual_gpa||a.gpa)||0));
  else if (sortMode==='gpa-asc') filtered.sort((a,b) => (parseFloat(a.actual_gpa||a.gpa)||0) - (parseFloat(b.actual_gpa||b.gpa)||0));
  else if (sortMode==='name') filtered.sort((a,b) => (a.name_initial||'').localeCompare(b.name_initial||''));

  var html = '';
  filtered.forEach(s => {
    var sid = s.student_id;
    if (s.isProtected) {
      html += '<div class="no-results"><span class="student-id" style="color:#f57c00;font-weight:700">' + sid + '</span><span>🔒 Protected</span></div>';
      return;
    }
    if (s.error) {
      html += '<div class="no-results"><span class="student-id" style="color:#c62828;font-weight:700">' + sid + '</span><span>⏳ Pending</span></div>';
      return;
    }
    var isOpen = expanded[sid];
    var gpa = s.actual_gpa || s.gpa || 'N/A';
    var gc = gpaClass(gpa);
    var cc = (s.courses||[]).filter(c => c['Course Code'] && !c['Course Code'].startsWith('Course Code')).length;
    html += '<div class="student-card"><div class="student-header" onclick="toggleDetails(\'' + sid + '\')">';
    html += '<div class="student-info"><div class="student-id">' + sid + ' <span class="count-badge">' + cc + ' courses</span></div>';
    html += '<div class="student-name">' + (s.name_initial||'N/A') + '</div></div>';
    html += '<div class="student-gpa"><div class="gpa-value ' + gc + '">' + gpa + '</div><div class="gpa-label">GPA</div></div>';
    html += '<div class="toggle-icon' + (isOpen?' open':'') + '">&#9654;</div></div>';
    if (isOpen) {
      html += '<div class="student-details open"><p class="detail-meta"><strong>Name:</strong> ' + (s.full_name||'') + '<br><strong>Credits:</strong> ' + (s.total_credit||'N/A') + '</p>';
      html += '<table class="course-table"><thead><tr><th>Course</th><th>Year</th><th>Att</th><th>Status</th><th>Note</th><th>Grade</th></tr></thead><tbody>';
      (s.courses||[]).forEach(c => {
        var code = c['Course Code']||'';
        if (code.startsWith('Course Code')) return;
        var grade = c['Grade']||'';
        var st = c['ExamStatus']||'';
        html += '<tr><td>'+code+'</td><td>'+(c['AcYear']||'')+'</td><td>'+(c['Attempt']||'')+'</td><td'+(st==='Absent'?' class="absent"':'')+'>'+ st+'</td><td>'+(c['Exam Note']||c['ExamNote']||'')+'</td><td class="'+gradeClass(grade)+'">'+grade+'</td></tr>';
      });
      html += '</tbody></table></div>';
    }
    html += '</div>';
  });
  if (!filtered.length) html = '<div style="text-align:center;color:#999;padding:40px">No students match your filter.</div>';
  document.getElementById('studentList').innerHTML = html;
}

// ===== ADMIN PANEL =====
function showAdmin() {
  document.getElementById('deptPage').classList.add('hidden');
  document.getElementById('resultsPage').classList.add('hidden');
  document.getElementById('adminPage').classList.remove('hidden');
  if (adminToken) { document.getElementById('adminLogin').classList.add('hidden'); document.getElementById('adminControls').classList.remove('hidden'); refreshAdmin(); }
  else { document.getElementById('adminLogin').classList.remove('hidden'); document.getElementById('adminControls').classList.add('hidden'); }
}
function hideAdmin() { document.getElementById('adminPage').classList.add('hidden'); showDeptPage(); }

function adminLoginSubmit() {
  var u = document.getElementById('adminUser').value.trim();
  var p = document.getElementById('adminPwd').value;
  fetch('/api/admin/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username:u, password:p})})
    .then(r=>r.json()).then(d => {
      if (d.ok) { adminToken = d.token; document.getElementById('adminLogin').classList.add('hidden'); document.getElementById('adminControls').classList.remove('hidden'); document.getElementById('adminError').textContent = ''; refreshAdmin(); }
      else { document.getElementById('adminError').textContent = d.error || 'Invalid credentials'; }
    }).catch(() => { document.getElementById('adminError').textContent = 'Connection error'; });
}

var adminHeaders = () => ({'Content-Type':'application/json', 'Authorization':'Bearer '+adminToken});

function refreshAdmin() {
  fetch('/api/admin/status', {headers: adminHeaders()}).then(r=>r.json()).then(d => {
    var msg = d.status?.message || 'Idle';
    var pct = d.status?.progress || 0;
    document.getElementById('scrapeStatus').textContent = (d.scrape_running ? '🟢 Running: ' : '⚪ ') + msg + ' | Last: ' + (d.last_run||'Never');
    document.getElementById('statusFill').style.width = Math.max(0,Math.min(100,pct)) + '%';
    document.getElementById('intervalSelect').value = String(d.interval_minutes || 30);
    document.getElementById('scrapeBtn').disabled = d.scrape_running;
    if (d.scrape_running) setTimeout(refreshAdmin, 3000);
  }).catch(()=>{});
  
  fetch('/api/admin/protected', {headers: adminHeaders()}).then(r=>r.json()).then(list => {
    if (!list.length) { document.getElementById('protectedList').innerHTML = '<p style="color:#999;font-size:0.85em">No protected students found.</p>'; return; }
    var h = '';
    list.forEach(p => {
      h += '<div class="prot-item"><div><span class="sid">' + p.student_id + '</span><span class="dept-tag">' + p.dept.toUpperCase() + '</span></div>';
      h += '<div><span class="status-tag ' + (p.has_password?'has-pwd':'no-pwd') + '">' + (p.has_password?'✓ Has password':'✗ No password') + '</span>';
      h += ' <button onclick="removeProtected(\'' + p.student_id + '\')">✕</button></div></div>';
    });
    document.getElementById('protectedList').innerHTML = h;
  }).catch(()=>{});
}

function triggerScrape() {
  var mode = document.getElementById('scrapeMode').value;
  var dept = document.getElementById('scrapeDept').value;
  document.getElementById('scrapeBtn').disabled = true;
  fetch('/api/admin/scrape', {method:'POST', headers: adminHeaders(), body: JSON.stringify({mode:mode, dept:dept})})
    .then(r=>r.json()).then(() => { setTimeout(refreshAdmin, 1000); }).catch(()=>{});
}

function updateInterval() {
  var val = document.getElementById('intervalSelect').value;
  fetch('/api/admin/config', {method:'POST', headers: adminHeaders(), body: JSON.stringify({interval_minutes:parseInt(val)})})
    .then(r=>r.json()).then(() => alert('Interval updated to ' + val + ' minutes')).catch(()=>{});
}

function updatePasswords() {
  var up = document.getElementById('newUserPwd').value;
  var ap = document.getElementById('newAdminPwd').value;
  var body = {};
  if (up) body.user_password = up;
  if (ap) body.admin_password = ap;
  fetch('/api/admin/config', {method:'POST', headers: adminHeaders(), body: JSON.stringify(body)})
    .then(r=>r.json()).then(() => { alert('Passwords updated'); document.getElementById('newUserPwd').value=''; document.getElementById('newAdminPwd').value=''; }).catch(()=>{});
}

function addProtected() {
  var sid = document.getElementById('protSid').value.trim().toUpperCase();
  var pwd = document.getElementById('protPwd').value;
  if (!sid) return;
  fetch('/api/admin/protected', {method:'POST', headers: adminHeaders(), body: JSON.stringify({student_id:sid, password:pwd})})
    .then(r=>r.json()).then(() => { document.getElementById('protSid').value=''; document.getElementById('protPwd').value=''; refreshAdmin(); }).catch(()=>{});
}

function removeProtected(sid) {
  fetch('/api/admin/protected', {method:'POST', headers: adminHeaders(), body: JSON.stringify({student_id:sid, password:''})})
    .then(r=>r.json()).then(() => refreshAdmin()).catch(()=>{});
}

// ===== INIT =====
if (localStorage.getItem('uok_user')) { showDeptPage(); }
if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js').catch(()=>{}); }
