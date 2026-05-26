'use strict';

let liveTimer = null;
var _editServerData = {};
var _editRuleData   = {};
var _editSlaveData  = {};

// ── Sidebar navigation ────────────────────────────────────────────────────────
document.querySelectorAll('.sidebar a[data-page]').forEach(function(link) {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        var pageId = this.dataset.page;
        document.querySelectorAll('.page').forEach(function(p) { p.classList.add('d-none'); });
        document.getElementById(pageId).classList.remove('d-none');
        document.querySelectorAll('.sidebar a').forEach(function(a) { a.classList.remove('active'); });
        this.classList.add('active');
        if (pageId === 'pDash')   loadDash();
        if (pageId === 'pRegs')   loadRegs();
        if (pageId === 'pServer') loadServers();
        if (pageId === 'pImport') loadExportPreview();
    });
});

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadDash() {
    try {
        var st  = await api('/status');
        var cfg = await api('/get-server-config');

        if (st.success) {
            set('dServers', st.servers_running.length);
            set('dSlaves',  st.slaves_configured);
            set('dRegs',    st.registers_configured);
            set('navStatus', st.servers_running.length + ' server(s) running');
        }

        if (cfg.success) {
            tbl('tServers', cfg.servers, function(s) {
                return '<td>' + s.server_id + '</td><td>' + s.ip + ':' + s.port + '</td>' +
                       '<td>' + s.vendor_name + '</td>' +
                       '<td><span class="badge bg-success">Running</span></td>';
            });
            tbl('tSlaves', cfg.slaves, function(s) {
                return '<td>' + s.server_id + '</td><td>' + s.slave_id + '</td>' +
                       '<td>' + s.co_size + '</td><td>' + s.di_size + '</td>' +
                       '<td>' + s.hr_size + '</td><td>' + s.ir_size + '</td>';
            });
        }
    } catch (e) {
        toast('Dashboard error: ' + e.message, 'danger');
    }
}

// ── Servers ───────────────────────────────────────────────────────────────────
async function loadServers() {
    var res = await api('/get-server-config');
    var wrap = document.getElementById('serverCardsWrap');
    if (!res.success) {
        wrap.innerHTML = '<div class="col-12"><p class="text-muted">Failed to load servers.</p></div>';
        return;
    }

    _editServerData = {};
    res.servers.forEach(function(s) { _editServerData[s.server_id] = s; });
    wrap.innerHTML = res.servers.length
        ? res.servers.map(function(s) {
            return '<div class="col-sm-6 col-lg-4">' +
                   '<div class="server-card">' +
                   '<div class="position-absolute top-0 end-0 m-2 d-flex gap-1">' +
                   '<button class="btn-row-edit" onclick="openEditServer(_editServerData[' + s.server_id + '])" title="Edit server">' +
                   '<i class="bi bi-pencil"></i></button>' +
                   '<button class="btn-row-del" onclick="deleteServer(' + s.server_id + ')" title="Delete server">' +
                   '<i class="bi bi-x-lg"></i></button>' +
                   '</div>' +
                   '<div class="server-card-title">Server ' + s.server_id + '</div>' +
                   '<div class="server-card-sub">' + s.ip + ':' + s.port + '</div>' +
                   '<div class="server-card-sub">' + s.vendor_name + ' &mdash; ' + s.version + '</div>' +
                   '</div></div>';
          }).join('')
        : '<div class="col-12"><p class="text-muted">No servers configured.</p></div>';

    _editSlaveData = {};
    res.slaves.forEach(function(s) { _editSlaveData[s.server_id + '_' + s.slave_id] = s; });
    tbl('tSlavesServer', res.slaves, function(s) {
        var key = s.server_id + '_' + s.slave_id;
        return '<td>' + s.server_id + '</td><td>' + s.slave_id + '</td>' +
               '<td>' + s.co_size + '</td><td>' + s.di_size + '</td>' +
               '<td>' + s.hr_size + '</td><td>' + s.ir_size + '</td>' +
               '<td class="d-flex gap-1">' +
               '<button class="btn-row-edit" onclick="openEditSlave(_editSlaveData[\'' + key + '\'])" title="Edit slave"><i class="bi bi-pencil"></i></button>' +
               '<button class="btn-row-del" onclick="deleteSlave(' + s.server_id + ',' + s.slave_id + ')" title="Delete slave"><i class="bi bi-trash3"></i></button>' +
               '</td>';
    });
}

async function addServer() {
    var body = {
        server_id:    int('asId'),
        ip:           val('asIp') || '0.0.0.0',
        port:         int('asPort'),
        vendor_name:  val('asVendor') || 'ModbusSimulator',
        product_code: val('asPcode') || 'MSIM',
        version:      val('asVer') || '1.0'
    };
    var res = await api('/servers/add', 'POST', body);
    if (!res.success) { toast('Error: ' + res.message, 'danger'); return; }

    // Auto-create slaves if num_slaves > 0
    var numSlaves = int('asSlaves') || 0;
    var slaveTasks = [];
    for (var i = 0; i < numSlaves; i++) {
        slaveTasks.push(api('/configure-server', 'POST', {
            // Use configure-server with a single-slave detailed payload per slave
        }));
    }
    // Build slaves inline via upsert_slave (we can reuse configure-server with DetailedServerConfig)
    if (numSlaves > 0) {
        var slaves = [];
        for (var j = 0; j < numSlaves; j++) {
            slaves.push({
                server_id: body.server_id,
                slave_id:  j,
                co_size:   int('asCo') || 100,
                di_size:   int('asDi') || 100,
                hr_size:   int('asHr') || 100,
                ir_size:   int('asIr') || 100
            });
        }
        await api('/configure-server', 'POST', { servers: [body], slaves: slaves });
    }

    toast(res.message || 'Server saved', 'success');
    loadServers();
}

async function deleteServer(serverId) {
    if (!confirm('Delete server ' + serverId + ' and all its slaves?')) return;
    var res = await api('/servers/' + serverId, 'DELETE');
    toast(res.message || (res.success ? 'Deleted' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) loadServers();
}

// ── Batch server config (kept for bulk operations) ─────────────────────────────
async function quickApply() {
    var body = {
        ip:        val('qIp'),
        port:      int('qPort'),
        instances: int('qInst'),
        slaves:    int('qSlaves'),
        identity:  { VendorName: 'ModbusSimulator', ProductCode: 'MSIM', MajorMinorRevision: '1.0' },
        register_sizes: { co: int('qCo'), di: int('qDi'), hr: int('qHr'), ir: int('qIr') }
    };
    var res = await api('/configure-server', 'POST', body);
    toast(res.message || (res.success ? 'Applied' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) { loadServers(); loadDash(); }
}

async function loadAdvanced() {
    var res = await api('/get-server-config');
    if (res.success)
        document.getElementById('advJson').value =
            JSON.stringify({ servers: res.servers, slaves: res.slaves }, null, 2);
}

async function advApply() {
    var body;
    try { body = JSON.parse(document.getElementById('advJson').value); }
    catch (e) { toast('Invalid JSON: ' + e.message, 'danger'); return; }
    var res = await api('/configure-server', 'POST', body);
    toast(res.message || (res.success ? 'Applied' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) { loadServers(); loadDash(); }
}

// ── Registers ─────────────────────────────────────────────────────────────────
async function loadRegs() {
    var res = await api('/get-registers');
    var wrap = document.getElementById('regsWrap');
    var rows = (res.success && res.registers) ? res.registers : [];

    if (!rows.length) {
        wrap.innerHTML = '<p class="text-muted p-3 mb-0">No register rules configured.</p>';
        return;
    }

    _editRuleData = {};
    rows.forEach(function(r) { _editRuleData[r.id] = r; });
    wrap.innerHTML =
        '<div class="table-responsive">' +
        '<table class="table table-sm table-hover mb-0" id="rulesTable">' +
        '<thead><tr>' +
          '<th>ID</th><th>Srv</th><th>Slave</th><th>Type</th>' +
          '<th>Addr</th><th>End</th><th>Mode</th><th>Config</th><th></th>' +
        '</tr></thead><tbody>' +
        rows.map(function(r) {
            var cfg = r.simulation_config || {};
            var f32badge = cfg.float32 ? ' <span class="badge bg-warning text-dark" style="font-size:.6rem;vertical-align:middle">f32</span>' : '';
            var cfgDisplay = Object.assign({}, cfg);
            delete cfgDisplay.float32;
            return '<tr>' +
                '<td style="color:#5a6470">' + r.id + '</td>' +
                '<td>' + (r.server_id != null ? r.server_id : '<span style="color:#5a6470">—</span>') + '</td>' +
                '<td>' + r.slave_id + '</td>' +
                '<td><code style="color:#6cb6ff">' + r.register_type + '</code></td>' +
                '<td>' + (r.address     != null ? r.address     : '—') + '</td>' +
                '<td>' + (r.address_end != null ? r.address_end : '—') + '</td>' +
                '<td><span class="badge bg-info text-dark mode-badge">' + (r.simulation_mode || '—') + '</span>' + f32badge + '</td>' +
                '<td><small style="color:#9daab6">' + JSON.stringify(cfgDisplay) + '</small></td>' +
                '<td class="d-flex gap-1">' +
                '<button class="btn-row-edit" onclick="openEditRule(_editRuleData[' + r.id + '])" title="Edit rule"><i class="bi bi-pencil"></i></button>' +
                '<button class="btn-row-del" onclick="deleteRule(' + r.id + ')" title="Delete rule"><i class="bi bi-trash3"></i></button>' +
                '</td>' +
                '</tr>';
        }).join('') +
        '</tbody></table></div>';
}

async function deleteRule(ruleId) {
    var res = await api('/rules/' + ruleId, 'DELETE');
    toast(res.success ? 'Rule ' + ruleId + ' deleted' : (res.message || 'Error'),
          res.success ? 'success' : 'danger');
    if (res.success) loadRegs();
}

async function addRule() {
    var configRaw = document.getElementById('arConfig').value || '{}';
    var simConfig;
    try { simConfig = JSON.parse(configRaw); }
    catch (e) { toast('simulation_config: invalid JSON — ' + e.message, 'danger'); return; }

    // Float32 checkbox is authoritative — sync it into the config object
    if (document.getElementById('arFloat32').checked) simConfig.float32 = true;
    else delete simConfig.float32;

    var srvVal = document.getElementById('arSrv').value.trim();
    var endVal = document.getElementById('arEnd').value.trim();
    var sizeVal = document.getElementById('arSize').value.trim();

    var body = {
        server_id:         srvVal  !== '' ? parseInt(srvVal,  10) : null,
        slave_id:          int('arSlave'),
        register_type:     val('arType'),
        address:           int('arAddr') || 0,
        address_end:       endVal  !== '' ? parseInt(endVal,  10) : null,
        register_size:     sizeVal !== '' ? parseInt(sizeVal, 10) : null,
        simulate:          document.getElementById('arSim').checked,
        simulation_mode:   val('arMode'),
        simulation_config: simConfig
    };

    var res = await api('/rules/add', 'POST', body);
    toast(
        res.success ? ('Rule #' + res.id + ' added') : ('Error: ' + (res.message || 'unknown')),
        res.success ? 'success' : 'danger'
    );
    if (res.success) loadRegs();
}

// Auto-fill sensible default configs when mode or float32 changes
function fillModeDefaults() {
    var mode = val('arMode');
    var f32 = document.getElementById('arFloat32').checked;
    var defaults = f32 ? {
        static:   '{"value": 0.0}',
        random:   '{"min": 0.0, "max": 500.0}',
        sine:     '{"amplitude": 100.0, "offset": 500.0, "period": 60}',
        ramp:     '{"min": 0.0, "max": 1000.0, "step": 0.5}',
        square:   '{"high": 100.0, "low": 0.0, "period": 20, "duty_cycle": 0.5}',
        equation: '{"equation": "sin(x * 0.1) * 100"}'
    } : {
        static:   '{"value": 0}',
        random:   '{"min": 0, "max": 500}',
        sine:     '{"amplitude": 100, "offset": 500, "period": 60}',
        ramp:     '{"min": 0, "max": 1000, "step": 10}',
        square:   '{"high": 1, "low": 0, "period": 20, "duty_cycle": 0.5}',
        equation: '{"equation": "(x + address) % 1000"}'
    };
    if (defaults[mode]) document.getElementById('arConfig').value = defaults[mode];
}

async function regApply() {
    var body;
    try { body = JSON.parse(document.getElementById('regJson').value); }
    catch (e) { toast('Invalid JSON: ' + e.message, 'danger'); return; }
    var res = await api('/configure-registers', 'POST', body);
    toast(res.message || (res.success ? 'Applied' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) loadRegs();
}

// ── Edit rule modal ───────────────────────────────────────────────────────────
var _editRuleModal = null;

function openEditRule(r) {
    var cfg = r.simulation_config || {};
    document.getElementById('erRuleId').value    = r.id;
    document.getElementById('erModalId').textContent = '#' + r.id;
    document.getElementById('erSrv').value       = r.server_id != null ? r.server_id : '';
    document.getElementById('erSlave').value     = r.slave_id;
    document.getElementById('erType').value      = r.register_type;
    document.getElementById('erAddr').value      = r.address != null ? r.address : 0;
    document.getElementById('erEnd').value       = r.address_end != null ? r.address_end : '';
    document.getElementById('erSize').value      = r.register_size != null ? r.register_size : '';
    document.getElementById('erMode').value      = r.simulation_mode || 'static';
    document.getElementById('erSim').checked     = !!r.simulate;
    document.getElementById('erFloat32').checked = !!cfg.float32;
    // Show config without the float32 key — the checkbox owns it
    var display = Object.assign({}, cfg);
    delete display.float32;
    document.getElementById('erConfig').value    = JSON.stringify(display, null, 2);
    if (!_editRuleModal) _editRuleModal = new bootstrap.Modal(document.getElementById('editRuleModal'));
    _editRuleModal.show();
}

async function saveEditRule() {
    var ruleId    = parseInt(document.getElementById('erRuleId').value, 10);
    var configRaw = document.getElementById('erConfig').value || '{}';
    var simConfig;
    try { simConfig = JSON.parse(configRaw); }
    catch (e) { toast('simulation_config: invalid JSON — ' + e.message, 'danger'); return; }

    // Float32 checkbox is authoritative
    if (document.getElementById('erFloat32').checked) simConfig.float32 = true;
    else delete simConfig.float32;

    var srvVal  = document.getElementById('erSrv').value.trim();
    var endVal  = document.getElementById('erEnd').value.trim();
    var sizeVal = document.getElementById('erSize').value.trim();

    var body = {
        server_id:         srvVal  !== '' ? parseInt(srvVal,  10) : null,
        slave_id:          parseInt(document.getElementById('erSlave').value, 10),
        register_type:     document.getElementById('erType').value,
        address:           parseInt(document.getElementById('erAddr').value,  10) || 0,
        address_end:       endVal  !== '' ? parseInt(endVal,  10) : null,
        register_size:     sizeVal !== '' ? parseInt(sizeVal, 10) : null,
        simulate:          document.getElementById('erSim').checked,
        simulation_mode:   document.getElementById('erMode').value,
        simulation_config: simConfig
    };

    var res = await api('/rules/' + ruleId, 'PUT', body);
    toast(res.message || (res.success ? 'Saved' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) { _editRuleModal.hide(); loadRegs(); }
}

// ── Edit server modal ─────────────────────────────────────────────────────────
var _editServerModal = null;

function openEditServer(s) {
    document.getElementById('esServerId').value  = s.server_id;
    document.getElementById('esModalId').textContent = '#' + s.server_id;
    document.getElementById('esIp').value        = s.ip;
    document.getElementById('esPort').value      = s.port;
    document.getElementById('esVendor').value    = s.vendor_name;
    document.getElementById('esPcode').value     = s.product_code;
    document.getElementById('esVer').value       = s.version;
    if (!_editServerModal) _editServerModal = new bootstrap.Modal(document.getElementById('editServerModal'));
    _editServerModal.show();
}

async function saveEditServer() {
    var serverId = parseInt(document.getElementById('esServerId').value, 10);
    var body = {
        server_id:    serverId,
        ip:           document.getElementById('esIp').value,
        port:         parseInt(document.getElementById('esPort').value, 10),
        vendor_name:  document.getElementById('esVendor').value,
        product_code: document.getElementById('esPcode').value,
        version:      document.getElementById('esVer').value
    };
    var res = await api('/servers/' + serverId, 'PUT', body);
    toast(res.message || (res.success ? 'Saved' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) { _editServerModal.hide(); loadServers(); }
}

// ── Edit slave modal ──────────────────────────────────────────────────────────
var _editSlaveModal = null;

function openEditSlave(s) {
    document.getElementById('slServerId').value      = s.server_id;
    document.getElementById('slSlaveId').value       = s.slave_id;
    document.getElementById('slModalId').textContent = 'Srv ' + s.server_id + ' / Slave ' + s.slave_id;
    document.getElementById('slCo').value = s.co_size;
    document.getElementById('slDi').value = s.di_size;
    document.getElementById('slHr').value = s.hr_size;
    document.getElementById('slIr').value = s.ir_size;
    if (!_editSlaveModal) _editSlaveModal = new bootstrap.Modal(document.getElementById('editSlaveModal'));
    _editSlaveModal.show();
}

async function saveEditSlave() {
    var serverId = parseInt(document.getElementById('slServerId').value, 10);
    var slaveId  = parseInt(document.getElementById('slSlaveId').value,  10);
    var body = {
        server_id: serverId,
        slave_id:  slaveId,
        co_size:   parseInt(document.getElementById('slCo').value, 10),
        di_size:   parseInt(document.getElementById('slDi').value, 10),
        hr_size:   parseInt(document.getElementById('slHr').value, 10),
        ir_size:   parseInt(document.getElementById('slIr').value, 10)
    };
    var res = await api('/slaves/' + serverId + '/' + slaveId, 'PUT', body);
    toast(res.message || (res.success ? 'Saved' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) { _editSlaveModal.hide(); loadServers(); }
}

async function deleteSlave(serverId, slaveId) {
    if (!confirm('Delete slave ' + slaveId + ' from server ' + serverId + '?')) return;
    var res = await api('/slaves/' + serverId + '/' + slaveId, 'DELETE');
    toast(res.message || (res.success ? 'Deleted' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) loadServers();
}

// ── Live view ─────────────────────────────────────────────────────────────────
function toggleLive() {
    if (liveTimer) {
        clearInterval(liveTimer);
        liveTimer = null;
        document.getElementById('liveBtn').textContent = 'Start';
        document.getElementById('liveDot').className = 'live-dot live-off';
    } else {
        fetchLive();
        liveTimer = setInterval(fetchLive, 2000);
        document.getElementById('liveBtn').textContent = 'Stop';
        document.getElementById('liveDot').className = 'live-dot live-on';
    }
}

async function fetchLive() {
    var res = await api('/live-values?server_id=' + val('lSrv'));
    var tbody = document.getElementById('liveTbody');

    if (!res.success) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3" style="color:#f85149">' + res.message + '</td></tr>';
        return;
    }
    if (!res.values || !res.values.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3" style="color:#8b949e">No simulated registers on this server</td></tr>';
        return;
    }

    tbody.innerHTML = res.values.map(function(v) {
        var valStr = v.value != null ? String(v.value) : '—';
        var f32badge = v.float32 ? ' <span class="badge bg-warning text-dark" style="font-size:.6rem">f32</span>' : '';
        return '<tr>' +
            '<td>' + v.slave_id + '</td>' +
            '<td><code style="color:#6cb6ff">' + v.register_type + '</code></td>' +
            '<td>' + v.address + '</td>' +
            '<td><strong>' + valStr + '</strong>' + f32badge + '</td>' +
            '<td><span class="badge bg-info text-dark mode-badge">' + (v.simulation_mode || '') + '</span></td>' +
            '</tr>';
    }).join('');
}

// ── Import / Export ───────────────────────────────────────────────────────────
function _exportSections() {
    var parts = [];
    if (document.getElementById('exServers') && document.getElementById('exServers').checked) parts.push('servers');
    if (document.getElementById('exSlaves')  && document.getElementById('exSlaves').checked)  parts.push('slaves');
    if (document.getElementById('exRegs')    && document.getElementById('exRegs').checked)    parts.push('registers');
    return parts.length ? parts.join(',') : 'servers,slaves,registers';
}

function exportConfig() {
    var sections = _exportSections();
    var a = document.createElement('a');
    a.href = '/export?sections=' + encodeURIComponent(sections);
    a.download = 'modsim-config.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

async function loadExportPreview() {
    try {
        var sections = _exportSections();
        var res = await api('/export?sections=' + encodeURIComponent(sections));
        var ta = document.getElementById('exportPreview');
        if (ta) ta.value = JSON.stringify(res, null, 2);
    } catch (e) {
        toast('Export preview error: ' + e.message, 'danger');
    }
}

async function restartServers() {
    var res = await api('/restart', 'POST');
    toast(res.message || (res.success ? 'Restarted' : 'Error'), res.success ? 'success' : 'warning');
    if (res.success) loadDash();
}

function loadImportFile() {
    var fileInput = document.getElementById('importFile');
    if (!fileInput.files.length) { toast('No file selected', 'warning'); return; }
    var reader = new FileReader();
    reader.onload = function(e) {
        document.getElementById('importJson').value = e.target.result;
    };
    reader.readAsText(fileInput.files[0]);
}

async function applyImport() {
    var raw = document.getElementById('importJson').value;
    var body;
    try { body = JSON.parse(raw); }
    catch (e) { toast('Invalid JSON: ' + e.message, 'danger'); return; }
    if (!confirm('This will REPLACE all current configuration. Continue?')) return;
    var res = await api('/import', 'POST', body);
    toast(res.message || (res.success ? 'Imported' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) loadDash();
}

// ── Utilities ─────────────────────────────────────────────────────────────────
async function api(path, method, body) {
    method = method || 'GET';
    var opts = { method: method, headers: { 'Content-Type': 'application/json' } };
    if (body !== undefined && body !== null) opts.body = JSON.stringify(body);
    var r = await fetch(path, opts);
    return r.json();
}

function val(id) { return document.getElementById(id).value; }
function int(id) { return parseInt(val(id), 10); }
function set(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

function tbl(id, rows, rowFn) {
    var tbody = document.querySelector('#' + id + ' tbody');
    if (!tbody) return;
    tbody.innerHTML = (rows && rows.length)
        ? rows.map(function(r) { return '<tr>' + rowFn(r) + '</tr>'; }).join('')
        : '<tr><td colspan="99" class="text-center py-3" style="color:#8b949e">None</td></tr>';
}

function toast(msg, type) {
    type = type || 'info';
    var id = 'toast-' + Date.now();
    var icon = { success: 'bi-check-circle-fill', danger: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
    var color = { success: '#3fb950', danger: '#f85149', warning: '#e3b341', info: '#58a6ff' };
    var c = color[type] || color.info;
    var ic = icon[type] || icon.info;
    document.getElementById('toastBox').insertAdjacentHTML('beforeend',
        '<div id="' + id + '" class="toast mb-2" role="alert">' +
        '<div class="d-flex align-items-center gap-2 toast-body" style="padding:.6rem .8rem">' +
        '<i class="bi ' + ic + '" style="color:' + c + ';flex-shrink:0"></i>' +
        '<span style="flex:1">' + msg + '</span>' +
        '<button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="toast" style="font-size:.7rem"></button>' +
        '</div></div>');
    var el = document.getElementById(id);
    new bootstrap.Toast(el, { delay: 5000 }).show();
    el.addEventListener('hidden.bs.toast', function() { el.remove(); });
}

// ── Mobile sidebar toggle ─────────────────────────────────────────────────────
(function() {
    var toggle   = document.getElementById('sidebarToggle');
    var sidebar  = document.querySelector('.sidebar');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (!toggle || !sidebar || !backdrop) return;

    function openSidebar()  { sidebar.classList.add('open');  backdrop.classList.add('open'); }
    function closeSidebar() { sidebar.classList.remove('open'); backdrop.classList.remove('open'); }

    toggle.addEventListener('click', function() {
        sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
    });
    backdrop.addEventListener('click', closeSidebar);

    // Close sidebar when a nav link is clicked on mobile
    sidebar.querySelectorAll('a[data-page]').forEach(function(a) {
        a.addEventListener('click', function() {
            if (window.innerWidth < 768) closeSidebar();
        });
    });
})();

// ── Boot ──────────────────────────────────────────────────────────────────────
loadDash();
