'use strict';

let liveTimer = null;
var _editServerData = {};
var _editRuleData   = {};
var _editSlaveData  = {};

var _regsRaw    = [];                                    // last-fetched rows, untouched
var _regsSort   = { key: null, dir: 0 };                  // dir: 0=none, 1=asc, -1=desc
var _regsFilter = { server: '', slave: '', type: '', q: '' };
var _serverVendorMap = {};                                // server_id -> vendor_name

// ── Router ────────────────────────────────────────────────────────────────────
var ROUTES = [
    { path: '/',              page: 'pDash',   title: 'Dashboard',       load: function() { loadDash(); } },
    { path: '/servers',       page: 'pServer', title: 'Servers',         load: function() { loadServers(); } },
    { path: '/registers',     page: 'pRegs',   title: 'Registers',       load: function() { loadRegs(); } },
    { path: '/live',          page: 'pLive',   title: 'Live View',       load: function() { loadLiveServers(); } },
    { path: '/import-export', page: 'pImport', title: 'Import / Export', load: function() { loadExportPreview(); updateImportModeHint(); } },
    { path: '/reference',     page: 'pRef',    title: 'Reference',       load: null }
];

function routeFor(path) {
    for (var i = 0; i < ROUTES.length; i++) {
        if (ROUTES[i].path === path) return ROUTES[i];
    }
    return ROUTES[0];
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.add('d-none'); });
    var el = document.getElementById(pageId);
    if (el) el.classList.remove('d-none');
    document.querySelectorAll('.sidebar a').forEach(function(a) { a.classList.remove('active'); });
    var link = document.querySelector('.sidebar a[data-page="' + pageId + '"]');
    if (link) link.classList.add('active');
}

function navigate(path, push) {
    var route = routeFor(path);
    showPage(route.page);
    document.title = route.title + ' · modSim';
    if (push) history.pushState({ path: route.path }, '', route.path);
    if (route.load) route.load();
}

window.addEventListener('popstate', function(e) {
    var path = (e.state && e.state.path) || location.pathname;
    navigate(path, false);
});

// ── Sidebar navigation ────────────────────────────────────────────────────────
document.querySelectorAll('.sidebar a[data-page]').forEach(function(link) {
    link.addEventListener('click', function(e) {
        e.preventDefault();
        navigate(link.getAttribute('href'), true);
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
            _serverVendorMap = {};
            cfg.servers.forEach(function(s) { _serverVendorMap[s.server_id] = s.vendor_name; });

            tbl('tServers', cfg.servers, function(s) {
                return '<td>' + s.server_id + '</td><td>' + s.ip + ':' + s.port + '</td>' +
                       '<td>' + escapeHtml(s.vendor_name) + '</td>' +
                       '<td><span class="badge bg-success">Running</span></td>';
            });
            tbl('tSlaves', cfg.slaves, function(s) {
                var vendor = _serverVendorMap[s.server_id];
                return '<td>' + s.server_id + '</td>' +
                       '<td>' + (vendor ? escapeHtml(vendor) : '<span style="color:var(--text-faint)">—</span>') + '</td>' +
                       '<td>' + s.slave_id + '</td>' +
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
    var wrap = document.getElementById('serverCardsWrap');
    wrap.innerHTML = '<div class="col-12">' + loadingStateHtml() + '</div>';

    var res = await api('/get-server-config');
    if (!res.success) {
        wrap.innerHTML = '<div class="col-12">' + emptyStateHtml('bi-exclamation-triangle', 'Failed to load servers.') + '</div>';
        return;
    }

    _editServerData = {};
    _serverVendorMap = {};
    res.servers.forEach(function(s) {
        _editServerData[s.server_id] = s;
        _serverVendorMap[s.server_id] = s.vendor_name;
    });
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
                   '<div class="server-card-sub">' + escapeHtml(s.vendor_name) + ' &mdash; ' + escapeHtml(s.version) + '</div>' +
                   '<div class="server-card-sub"><span class="badge ' + (s.zero_based === false ? 'bg-warning text-dark' : 'bg-secondary') + '" style="font-size:.6rem">' + (s.zero_based === false ? '1-based' : '0-based') + '</span></div>' +
                   '</div></div>';
          }).join('')
        : '<div class="col-12">' + emptyStateHtml('bi-hdd-network', 'No servers configured.', 'Add Server', 'openAddServer()') + '</div>';

    _editSlaveData = {};
    res.slaves.forEach(function(s) { _editSlaveData[s.server_id + '_' + s.slave_id] = s; });
    tbl('tSlavesServer', res.slaves, function(s) {
        var key = s.server_id + '_' + s.slave_id;
        var vendor = _serverVendorMap[s.server_id];
        return '<td>' + s.server_id + '</td>' +
               '<td>' + (vendor ? escapeHtml(vendor) : '<span style="color:var(--text-faint)">—</span>') + '</td>' +
               '<td>' + s.slave_id + '</td>' +
               '<td>' + s.co_size + '</td><td>' + s.di_size + '</td>' +
               '<td>' + s.hr_size + '</td><td>' + s.ir_size + '</td>' +
               '<td class="d-flex gap-1">' +
               '<button class="btn-row-edit" onclick="openEditSlave(_editSlaveData[\'' + key + '\'])" title="Edit slave"><i class="bi bi-pencil"></i></button>' +
               '<button class="btn-row-del" onclick="deleteSlave(' + s.server_id + ',' + s.slave_id + ')" title="Delete slave"><i class="bi bi-trash3"></i></button>' +
               '</td>';
    });
}

async function deleteServer(serverId) {
    var vendor = _serverVendorMap[serverId];
    var label = 'server ' + serverId + (vendor ? ' (' + vendor + ')' : '');
    if (!confirm('Delete ' + label + ' and all its slaves?')) return;
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
        zero_based: val('qBase') !== 'false',
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
var REGS_COLUMNS = [
    { key: 'id',              label: 'ID',    numeric: true },
    { key: 'server_id',       label: 'Srv',   numeric: true },
    { key: 'slave_id',        label: 'Slave', numeric: true },
    { key: 'register_type',   label: 'Type',  numeric: false },
    { key: 'address',         label: 'Addr',  numeric: true },
    { key: 'address_end',     label: 'End',   numeric: true },
    { key: 'simulation_mode', label: 'Mode',  numeric: false }
];

async function loadRegs() {
    var wrap = document.getElementById('regsWrap');
    wrap.innerHTML = loadingStateHtml();

    var res = await api('/get-registers');
    _regsRaw = (res.success && res.registers) ? res.registers : [];

    _editRuleData = {};
    _regsRaw.forEach(function(r) { _editRuleData[r.id] = r; });

    await refreshServerVendorMap();
    populateRegsServerFilter();
    renderRegsTable();
}

async function refreshServerVendorMap() {
    var cfg = await api('/get-server-config');
    _serverVendorMap = {};
    if (cfg.success && cfg.servers) {
        cfg.servers.forEach(function(s) { _serverVendorMap[s.server_id] = s.vendor_name; });
    }
}

function populateRegsServerFilter() {
    var sel = document.getElementById('rfServer');
    if (!sel) return;
    var current = sel.value;
    var servers = Array.from(new Set(_regsRaw.map(function(r) { return r.server_id; })
        .filter(function(id) { return id != null; }))).sort(function(a, b) { return a - b; });
    sel.innerHTML = '<option value="">All Servers</option>' + serverOptionsHtml(servers);
    sel.value = current;
}

function applyRegsFilterSort(rows) {
    var f = _regsFilter;
    var filtered = rows.filter(function(r) {
        if (f.server !== '' && String(r.server_id) !== f.server) return false;
        if (f.slave  !== '' && String(r.slave_id)  !== f.slave)  return false;
        if (f.type   !== '' && r.register_type !== f.type) return false;
        if (f.q) {
            var cfg = JSON.stringify(r.simulation_config || {});
            var haystack = [r.id, r.address, r.address_end, r.simulation_mode, cfg]
                .join(' ').toLowerCase();
            if (haystack.indexOf(f.q.toLowerCase()) === -1) return false;
        }
        return true;
    });

    if (!_regsSort.key || !_regsSort.dir) return filtered;
    var col = REGS_COLUMNS.find(function(c) { return c.key === _regsSort.key; });
    var dir = _regsSort.dir;
    return filtered.slice().sort(function(a, b) {
        var av = a[_regsSort.key], bv = b[_regsSort.key];
        if (av == null && bv == null) return 0;
        if (av == null) return 1;   // nulls last regardless of direction
        if (bv == null) return -1;
        if (col && col.numeric) return (av - bv) * dir;
        return String(av).localeCompare(String(bv)) * dir;
    });
}

function renderRegsTable() {
    var wrap = document.getElementById('regsWrap');
    var caption = document.getElementById('regsCaption');

    if (!_regsRaw.length) {
        wrap.innerHTML = emptyStateHtml('bi-table', 'No register rules configured.', 'Add Rule', 'openAddRule()');
        if (caption) caption.textContent = '';
        return;
    }

    var rows = applyRegsFilterSort(_regsRaw);
    if (caption) caption.textContent = 'Showing ' + rows.length + ' of ' + _regsRaw.length + ' rule(s)';

    if (!rows.length) {
        wrap.innerHTML = emptyStateHtml('bi-funnel', 'No rules match your filters.', 'Clear filters', 'clearRegsFilters()');
        return;
    }

    var thead = '<tr>' + REGS_COLUMNS.map(function(c) {
        var active = _regsSort.key === c.key && _regsSort.dir !== 0;
        var icon = active ? (_regsSort.dir === 1 ? 'bi-caret-up-fill' : 'bi-caret-down-fill') : '';
        var th = '<th class="th-sortable' + (active ? ' active' : '') + '" onclick="onRegsHeaderClick(\'' + c.key + '\')">' +
               c.label + (icon ? ' <i class="bi ' + icon + ' sort-icon"></i>' : '') + '</th>';
        return c.key === 'server_id' ? th + '<th>Vendor</th>' : th;
    }).join('') + '<th>Config</th><th></th></tr>';

    wrap.innerHTML =
        '<div class="table-responsive">' +
        '<table class="table table-sm table-hover table-compact mb-0" id="rulesTable">' +
        '<thead>' + thead + '</thead><tbody>' +
        rows.map(function(r) {
            var cfg = r.simulation_config || {};
            var f32badge = cfg.float32 ? ' <span class="badge bg-warning text-dark" style="font-size:.6rem;vertical-align:middle">f32</span>' : '';
            var cfgDisplay = Object.assign({}, cfg);
            delete cfgDisplay.float32;
            var vendor = r.server_id != null ? _serverVendorMap[r.server_id] : null;
            return '<tr>' +
                '<td style="color:var(--text-faint)">' + r.id + '</td>' +
                '<td>' + (r.server_id != null ? r.server_id : '<span style="color:var(--text-faint)">—</span>') + '</td>' +
                '<td>' + (vendor ? escapeHtml(vendor) : '<span style="color:var(--text-faint)">—</span>') + '</td>' +
                '<td>' + r.slave_id + '</td>' +
                '<td><code style="color:var(--accent)">' + r.register_type + '</code></td>' +
                '<td>' + (r.address     != null ? r.address     : '—') + '</td>' +
                '<td>' + (r.address_end != null ? r.address_end : '—') + '</td>' +
                '<td><span class="badge bg-info text-dark mode-badge">' + (r.simulation_mode || '—') + '</span>' + f32badge + '</td>' +
                '<td><small style="color:var(--text-muted)">' + JSON.stringify(cfgDisplay) + '</small></td>' +
                '<td class="d-flex gap-1">' +
                '<button class="btn-row-edit" onclick="openEditRule(_editRuleData[' + r.id + '])" title="Edit rule"><i class="bi bi-pencil"></i></button>' +
                '<button class="btn-row-del" onclick="deleteRule(' + r.id + ')" title="Delete rule"><i class="bi bi-trash3"></i></button>' +
                '</td>' +
                '</tr>';
        }).join('') +
        '</tbody></table></div>';
}

function onRegsHeaderClick(key) {
    if (_regsSort.key !== key) {
        _regsSort = { key: key, dir: 1 };
    } else if (_regsSort.dir === 1) {
        _regsSort.dir = -1;
    } else if (_regsSort.dir === -1) {
        _regsSort = { key: null, dir: 0 };
    } else {
        _regsSort.dir = 1;
    }
    renderRegsTable();
}

var _regsFilterDebounce = null;
function onRegsFilterChange() {
    clearTimeout(_regsFilterDebounce);
    _regsFilterDebounce = setTimeout(function() {
        _regsFilter = {
            server: val('rfServer'),
            slave:  val('rfSlave'),
            type:   val('rfType'),
            q:      val('rfSearch').trim()
        };
        renderRegsTable();
    }, 150);
}

function clearRegsFilters() {
    ['rfServer', 'rfSlave', 'rfType', 'rfSearch'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.value = '';
    });
    _regsFilter = { server: '', slave: '', type: '', q: '' };
    renderRegsTable();
}

async function deleteRule(ruleId) {
    var res = await api('/rules/' + ruleId, 'DELETE');
    toast(res.success ? 'Rule ' + ruleId + ' deleted' : (res.message || 'Error'),
          res.success ? 'success' : 'danger');
    if (res.success) loadRegs();
}

// Auto-fill sensible default configs when mode or float32 changes
function fillModeDefaults() {
    var mode = val('erMode');
    var f32 = document.getElementById('erFloat32').checked;
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
    if (defaults[mode]) document.getElementById('erConfig').value = defaults[mode];
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

function populateEditRuleServerSelect(ensureId) {
    var sel = document.getElementById('erSrv');
    if (!sel) return;
    var ids = Object.keys(_serverVendorMap).map(Number);
    if (ensureId != null && ids.indexOf(ensureId) === -1) ids.push(ensureId);
    ids.sort(function(a, b) { return a - b; });
    sel.innerHTML = '<option value="">All Servers</option>' +
        ids.map(function(id) {
            var vendor = _serverVendorMap[id];
            var label = 'Server ' + id + (vendor ? ' — ' + vendor : ' — (unknown server)');
            return '<option value="' + id + '">' + escapeHtml(label) + '</option>';
        }).join('');
}

function openEditRule(r) {
    var modal = document.getElementById('editRuleModal');
    var isCreate = !r;
    modal.dataset.mode = isCreate ? 'create' : 'edit';
    document.getElementById('erModalVerb').textContent = isCreate ? 'Add Rule' : 'Edit Rule';
    document.getElementById('erModalId').textContent   = isCreate ? '' : ('#' + r.id);
    document.getElementById('erSaveLabel').textContent = isCreate ? 'Add Rule' : 'Save Rule';

    populateEditRuleServerSelect(isCreate ? null : r.server_id);

    var cfg = isCreate ? {} : (r.simulation_config || {});
    document.getElementById('erRuleId').value    = isCreate ? '' : r.id;
    document.getElementById('erSrv').value       = isCreate ? '' : (r.server_id != null ? r.server_id : '');
    document.getElementById('erSlave').value     = isCreate ? 0  : r.slave_id;
    document.getElementById('erType').value      = isCreate ? 'ir' : r.register_type;
    document.getElementById('erAddr').value      = isCreate ? 0  : (r.address != null ? r.address : 0);
    document.getElementById('erEnd').value       = isCreate ? '' : (r.address_end != null ? r.address_end : '');
    document.getElementById('erSize').value      = isCreate ? '' : (r.register_size != null ? r.register_size : '');
    document.getElementById('erMode').value      = isCreate ? 'static' : (r.simulation_mode || 'static');
    document.getElementById('erSim').checked     = isCreate ? true : !!r.simulate;
    document.getElementById('erFloat32').checked = isCreate ? false : !!cfg.float32;
    if (isCreate) {
        document.getElementById('erConfig').value = '{"value": 0}';
    } else {
        // Show config without the float32 key — the checkbox owns it
        var display = Object.assign({}, cfg);
        delete display.float32;
        document.getElementById('erConfig').value = JSON.stringify(display, null, 2);
    }

    if (!_editRuleModal) _editRuleModal = new bootstrap.Modal(modal);
    _editRuleModal.show();
}

function openAddRule() { openEditRule(null); }

async function saveEditRule() {
    var modal = document.getElementById('editRuleModal');
    var isCreate = modal.dataset.mode === 'create';
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

    if (isCreate) {
        var res = await api('/rules/add', 'POST', body);
        toast(
            res.success ? ('Rule #' + res.id + ' added') : ('Error: ' + (res.message || 'unknown')),
            res.success ? 'success' : 'danger'
        );
        if (res.success) { _editRuleModal.hide(); loadRegs(); }
        return;
    }

    var ruleId = parseInt(document.getElementById('erRuleId').value, 10);
    var res = await api('/rules/' + ruleId, 'PUT', body);
    toast(res.message || (res.success ? 'Saved' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) { _editRuleModal.hide(); loadRegs(); }
}

// ── Edit server modal ─────────────────────────────────────────────────────────
var _editServerModal = null;

function openEditServer(s) {
    var modal = document.getElementById('editServerModal');
    var isCreate = !s;
    modal.dataset.mode = isCreate ? 'create' : 'edit';
    document.getElementById('esModalVerb').textContent = isCreate ? 'Add Server' : 'Edit Server';
    document.getElementById('esModalId').textContent   = isCreate ? '' : ('#' + s.server_id);
    document.getElementById('esSaveLabel').textContent = isCreate ? 'Add Server' : 'Save Server';

    var idInput = document.getElementById('esServerId');
    if (isCreate) {
        var existingIds = Object.keys(_editServerData).map(Number);
        idInput.value = existingIds.length ? (Math.max.apply(null, existingIds) + 1) : 0;
    } else {
        idInput.value = s.server_id;
    }
    idInput.readOnly = !isCreate;
    document.getElementById('esIdHelp').textContent = isCreate ? 'Next available — change if you need a specific ID' : '';

    document.getElementById('esIp').value        = isCreate ? '0.0.0.0'         : s.ip;
    document.getElementById('esPort').value      = isCreate ? 502              : s.port;
    document.getElementById('esVendor').value    = isCreate ? 'ModbusSimulator' : s.vendor_name;
    document.getElementById('esPcode').value     = isCreate ? 'MSIM'            : s.product_code;
    document.getElementById('esVer').value       = isCreate ? '1.0'             : s.version;
    document.getElementById('esBase').value      = isCreate ? 'true' : (s.zero_based === false ? 'false' : 'true');

    document.getElementById('esQuickSlaves').classList.toggle('d-none', !isCreate);
    if (isCreate) {
        document.getElementById('esNumSlaves').value = 1;
        document.getElementById('esQCo').value = 100;
        document.getElementById('esQDi').value = 100;
        document.getElementById('esQHr').value = 100;
        document.getElementById('esQIr').value = 100;
    }

    if (!_editServerModal) _editServerModal = new bootstrap.Modal(modal);
    _editServerModal.show();
}

function openAddServer() { openEditServer(null); }

async function saveEditServer() {
    var modal = document.getElementById('editServerModal');
    var isCreate = modal.dataset.mode === 'create';
    var serverId = parseInt(document.getElementById('esServerId').value, 10);
    if (isNaN(serverId)) { toast('Server ID is required', 'danger'); return; }

    if (isCreate && _editServerData[serverId]) {
        if (!confirm('Server ' + serverId + ' already exists and will be overwritten — continue?')) return;
    }

    var body = {
        server_id:    serverId,
        ip:           document.getElementById('esIp').value,
        port:         parseInt(document.getElementById('esPort').value, 10),
        vendor_name:  document.getElementById('esVendor').value,
        product_code: document.getElementById('esPcode').value,
        version:      document.getElementById('esVer').value,
        zero_based:   document.getElementById('esBase').value !== 'false'
    };

    var res = isCreate
        ? await api('/servers/add', 'POST', body)
        : await api('/servers/' + serverId, 'PUT', body);
    if (!res.success) { toast('Error: ' + res.message, 'danger'); return; }

    if (isCreate) {
        var numSlaves = parseInt(document.getElementById('esNumSlaves').value, 10) || 0;
        var coSize = parseInt(document.getElementById('esQCo').value, 10) || 100;
        var diSize = parseInt(document.getElementById('esQDi').value, 10) || 100;
        var hrSize = parseInt(document.getElementById('esQHr').value, 10) || 100;
        var irSize = parseInt(document.getElementById('esQIr').value, 10) || 100;
        // One upsert per slave — non-destructive, unlike /configure-server which
        // replaces the *entire* server/slave topology and would wipe every other server.
        for (var j = 0; j < numSlaves; j++) {
            await api('/slaves/' + serverId + '/' + j, 'PUT', {
                server_id: serverId, slave_id: j,
                co_size: coSize, di_size: diSize, hr_size: hrSize, ir_size: irSize
            });
        }
    }

    toast(res.message || 'Saved', 'success');
    _editServerModal.hide();
    loadServers();
}

// ── Edit slave modal ──────────────────────────────────────────────────────────
var _editSlaveModal = null;

function openEditSlave(s) {
    var modal = document.getElementById('editSlaveModal');
    var isCreate = !s;
    modal.dataset.mode = isCreate ? 'create' : 'edit';
    document.getElementById('slModalVerb').textContent = isCreate ? 'Add Slave' : 'Edit Slave';
    document.getElementById('slModalId').textContent   = isCreate ? '' : ('Srv ' + s.server_id + ' / Slave ' + s.slave_id);
    document.getElementById('slSaveLabel').textContent = isCreate ? 'Add Slave' : 'Save Slave';

    var srvInput   = document.getElementById('slServerId');
    var slaveInput = document.getElementById('slSlaveId');

    var ids = Object.keys(_serverVendorMap).map(Number);
    if (!isCreate && ids.indexOf(s.server_id) === -1) ids.push(s.server_id);
    ids.sort(function(a, b) { return a - b; });
    srvInput.innerHTML = (isCreate ? '<option value="">Select a server…</option>' : '') + serverOptionsHtml(ids);
    srvInput.value   = isCreate ? '' : s.server_id;
    slaveInput.value = isCreate ? '' : s.slave_id;
    srvInput.disabled    = !isCreate;
    slaveInput.readOnly  = !isCreate;
    document.getElementById('slServerHelp').textContent = isCreate && !ids.length ? 'No servers configured — add one first' : '';
    document.getElementById('slSlaveHelp').textContent  = isCreate ? 'Must be unique for this server' : '';

    document.getElementById('slCo').value = isCreate ? 100 : s.co_size;
    document.getElementById('slDi').value = isCreate ? 100 : s.di_size;
    document.getElementById('slHr').value = isCreate ? 100 : s.hr_size;
    document.getElementById('slIr').value = isCreate ? 100 : s.ir_size;

    if (!_editSlaveModal) _editSlaveModal = new bootstrap.Modal(modal);
    _editSlaveModal.show();
}

function openAddSlave() { openEditSlave(null); }

async function saveEditSlave() {
    var modal = document.getElementById('editSlaveModal');
    var isCreate = modal.dataset.mode === 'create';
    var serverId = parseInt(document.getElementById('slServerId').value, 10);
    var slaveId  = parseInt(document.getElementById('slSlaveId').value,  10);
    if (isNaN(serverId) || isNaN(slaveId)) { toast('Server ID and Slave ID are required', 'danger'); return; }

    if (isCreate) {
        if (!_editServerData[serverId]) {
            toast('Server ' + serverId + ' does not exist — add it first', 'danger');
            return;
        }
        if (_editSlaveData[serverId + '_' + slaveId]) {
            if (!confirm('Slave ' + slaveId + ' already exists on server ' + serverId + ' and will be overwritten — continue?')) return;
        }
    }

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
    var vendor = _serverVendorMap[serverId];
    var label = 'server ' + serverId + (vendor ? ' (' + vendor + ')' : '');
    if (!confirm('Delete slave ' + slaveId + ' from ' + label + '?')) return;
    var res = await api('/slaves/' + serverId + '/' + slaveId, 'DELETE');
    toast(res.message || (res.success ? 'Deleted' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) loadServers();
}

// ── Live view ─────────────────────────────────────────────────────────────────
function serverOptionsHtml(ids) {
    return ids.map(function(id) {
        var vendor = _serverVendorMap[id];
        var label = 'Server ' + id + (vendor ? ' — ' + vendor : '');
        return '<option value="' + id + '">' + escapeHtml(label) + '</option>';
    }).join('');
}

function _populateServerSelect(sel, optionsHtml, ids) {
    if (!sel) return;
    var current = sel.value;
    sel.innerHTML = optionsHtml;
    sel.value = ids.map(String).indexOf(current) !== -1 ? current : sel.options[0].value;
}

async function loadLiveServers() {
    var lSel = document.getElementById('lSrv');
    var dSel = document.getElementById('drwServer');
    if (!lSel && !dSel) return;

    await refreshServerVendorMap();
    var ids = Object.keys(_serverVendorMap).map(Number).sort(function(a, b) { return a - b; });
    var optionsHtml = ids.length ? serverOptionsHtml(ids) : '<option value="0">Server 0</option>';

    _populateServerSelect(lSel, optionsHtml, ids);
    _populateServerSelect(dSel, optionsHtml, ids);
}

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
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3" style="color:var(--danger)">' + res.message + '</td></tr>';
        return;
    }
    if (!res.values || !res.values.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center py-3" style="color:var(--text-muted)">No simulated registers on this server</td></tr>';
        return;
    }

    tbody.innerHTML = res.values.map(function(v) {
        var valStr = v.value != null ? String(v.value) : '—';
        var f32badge = v.float32 ? ' <span class="badge bg-warning text-dark" style="font-size:.6rem">f32</span>' : '';
        return '<tr>' +
            '<td>' + v.slave_id + '</td>' +
            '<td><code style="color:var(--accent)">' + v.register_type + '</code></td>' +
            '<td>' + v.address + '</td>' +
            '<td><strong>' + valStr + '</strong>' + f32badge + '</td>' +
            '<td><span class="badge bg-info text-dark mode-badge">' + (v.simulation_mode || '') + '</span></td>' +
            '</tr>';
    }).join('');
}

// ── Direct register read/write ──────────────────────────────────────────────────
function onDrwTypeChange() {
    var type = val('drwType');
    var f32 = document.getElementById('drwFloat32');
    var isBit = (type === 'co' || type === 'di');
    f32.disabled = isBit;
    if (isBit) f32.checked = false;
    checkRuleOverlap();
}

async function checkRuleOverlap() {
    var banner = document.getElementById('drwWarning');
    var serverId = int('drwServer');
    var slaveId  = int('drwSlave');
    var type     = val('drwType');
    var addr     = int('drwAddr');
    if (isNaN(serverId) || isNaN(slaveId) || isNaN(addr)) { banner.classList.add('d-none'); return; }

    var res = await api('/get-registers');
    if (!res.success) { banner.classList.add('d-none'); return; }

    var match = (res.registers || []).find(function(r) {
        if (!r.simulate) return false;
        if (r.server_id !== serverId) return false;
        if (r.slave_id  !== slaveId)  return false;
        if (r.register_type !== type) return false;
        var start = r.address != null ? r.address : 0;
        var end = r.address_end != null ? r.address_end : start;
        return addr >= start && addr <= end;
    });

    if (match) {
        banner.innerHTML = '<i class="bi bi-exclamation-triangle-fill"></i>Address ' + addr +
            ' is covered by an active simulation rule (mode: ' + (match.simulation_mode || 'unknown') +
            ') — writes here will be overwritten within ~1s.';
        banner.classList.remove('d-none');
    } else {
        banner.classList.add('d-none');
    }
}

function drwParams() {
    return {
        server_id: int('drwServer'),
        slave_id: int('drwSlave'),
        register_type: val('drwType'),
        address: int('drwAddr')
    };
}

async function directRead() {
    var p = drwParams();
    var count = int('drwCount') || 1;
    var float32 = document.getElementById('drwFloat32').checked;
    var qs = new URLSearchParams({
        server_id: p.server_id, slave_id: p.slave_id, register_type: p.register_type,
        address: p.address, count: count, float32: float32
    }).toString();
    var res = await api('/registers/read?' + qs);
    var out = document.getElementById('drwResult');
    if (!res.success) {
        out.innerHTML = '<span style="color:var(--danger)">' + res.message + '</span>';
        return;
    }
    out.innerHTML = '<code style="color:var(--accent)">' + JSON.stringify(res.values) + '</code>';
    checkRuleOverlap();
}

async function directWrite() {
    var p = drwParams();
    var float32 = document.getElementById('drwFloat32').checked;
    var raw = val('drwValues').trim();
    if (!raw) { toast('Enter at least one value to write', 'danger'); return; }
    var values = raw.split(',').map(function(s) {
        var t = s.trim();
        return float32 ? parseFloat(t) : parseInt(t, 10);
    });
    if (values.some(function(v) { return isNaN(v); })) { toast('Invalid value(s)', 'danger'); return; }

    var body = Object.assign({}, p, { values: values, float32: float32 });
    var res = await api('/registers/write', 'POST', body);
    toast(res.message || (res.success ? 'Written' : 'Error'), res.success ? 'success' : 'danger');
    if (res.success) directRead();
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

function updateImportModeHint() {
    var mode = document.getElementById('importMode').value;
    var hint = document.getElementById('importModeHint');
    if (mode === 'replace') {
        hint.innerHTML = '<i class="bi bi-exclamation-triangle-fill"></i>Replace wipes each supplied section entirely before inserting — servers/slaves/rules not in the JSON for that section are removed.';
        hint.classList.add('import-warning');
    } else {
        hint.innerHTML = '<i class="bi bi-info-circle"></i>Merge upserts servers &amp; slaves by id and rules by (server, slave, type, address); anything not in the JSON is left untouched. Re-importing is idempotent.';
        hint.classList.remove('import-warning');
    }
}

async function applyImport() {
    var raw = document.getElementById('importJson').value;
    var body;
    try { body = JSON.parse(raw); }
    catch (e) { toast('Invalid JSON: ' + e.message, 'danger'); return; }
    var mode = document.getElementById('importMode').value;
    body.mode = mode;
    if (mode === 'replace' &&
        !confirm('REPLACE mode: each section present in the JSON will be wiped and replaced. Continue?')) return;
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

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function(c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

function val(id) { return document.getElementById(id).value; }
function int(id) { return parseInt(val(id), 10); }
function set(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

function tbl(id, rows, rowFn) {
    var tbody = document.querySelector('#' + id + ' tbody');
    if (!tbody) return;
    tbody.innerHTML = (rows && rows.length)
        ? rows.map(function(r) { return '<tr>' + rowFn(r) + '</tr>'; }).join('')
        : '<tr><td colspan="99" class="text-center py-3" style="color:var(--text-muted)">None</td></tr>';
}

// ── Empty / loading state helpers ───────────────────────────────────────────────
function emptyStateHtml(icon, message, ctaLabel, ctaOnclick) {
    var cta = ctaLabel
        ? '<button class="btn btn-sm btn-outline-secondary mt-1" onclick="' + ctaOnclick + '">' + ctaLabel + '</button>'
        : '';
    return '<div class="empty-state"><i class="bi ' + icon + '"></i><span>' + message + '</span>' + cta + '</div>';
}

function loadingStateHtml(message) {
    return '<div class="loading-state"><span class="spinner-border spinner-border-sm"></span>' +
           '<span>' + (message || 'Loading…') + '</span></div>';
}

function toast(msg, type) {
    type = type || 'info';
    var id = 'toast-' + Date.now();
    var icon = { success: 'bi-check-circle-fill', danger: 'bi-x-circle-fill', warning: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill' };
    var color = { success: 'var(--success)', danger: 'var(--danger)', warning: 'var(--warning)', info: 'var(--accent)' };
    var c = color[type] || color.info;
    var ic = icon[type] || icon.info;
    document.getElementById('toastBox').insertAdjacentHTML('beforeend',
        '<div id="' + id + '" class="toast mb-2" role="alert">' +
        '<div class="d-flex align-items-center gap-2 toast-body" style="padding:.6rem .8rem">' +
        '<i class="bi ' + ic + '" style="color:' + c + ';flex-shrink:0"></i>' +
        '<span style="flex:1">' + msg + '</span>' +
        '<button type="button" class="btn-close ms-auto" data-bs-dismiss="toast" style="font-size:.7rem"></button>' +
        '</div></div>');
    var el = document.getElementById(id);
    new bootstrap.Toast(el, { delay: 5000 }).show();
    el.addEventListener('hidden.bs.toast', function() { el.remove(); });
}

// ── Sidebar toggle (mobile off-canvas + desktop icon-rail collapse) ────────────
(function() {
    var toggle   = document.getElementById('sidebarToggle');
    var sidebar  = document.querySelector('.sidebar');
    var backdrop = document.getElementById('sidebarBackdrop');
    if (!toggle || !sidebar || !backdrop) return;

    var COLLAPSE_KEY = 'modsim-sidebar-collapsed';

    function isMobile() { return window.innerWidth < 768; }

    function openSidebar()  { sidebar.classList.add('open');  backdrop.classList.add('open'); }
    function closeSidebar() { sidebar.classList.remove('open'); backdrop.classList.remove('open'); }

    function setCollapsed(collapsed) {
        document.body.classList.toggle('sidebar-collapsed', collapsed);
        localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
    }

    // Restore persisted desktop collapse state on load.
    if (!isMobile() && localStorage.getItem(COLLAPSE_KEY) === '1') {
        document.body.classList.add('sidebar-collapsed');
    }

    toggle.addEventListener('click', function() {
        if (isMobile()) {
            sidebar.classList.contains('open') ? closeSidebar() : openSidebar();
        } else {
            setCollapsed(!document.body.classList.contains('sidebar-collapsed'));
        }
    });
    backdrop.addEventListener('click', closeSidebar);

    // Close sidebar when a nav link is clicked on mobile
    sidebar.querySelectorAll('a[data-page]').forEach(function(a) {
        a.addEventListener('click', function() {
            if (isMobile()) closeSidebar();
        });
    });
})();

// ── Theme toggle ──────────────────────────────────────────────────────────────
(function() {
    var toggle = document.getElementById('themeToggle');
    var icon   = document.getElementById('themeIcon');
    if (!toggle || !icon) return;

    function effectiveTheme() {
        var explicit = document.documentElement.dataset.theme;
        if (explicit === 'light' || explicit === 'dark') return explicit;
        return (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) ? 'light' : 'dark';
    }

    function syncIcon() {
        icon.className = 'bi ' + (effectiveTheme() === 'dark' ? 'bi-sun' : 'bi-moon-stars');
    }

    toggle.addEventListener('click', function() {
        var next = effectiveTheme() === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        localStorage.setItem('modsim-theme', next);
        syncIcon();
    });

    syncIcon();
})();

// ── Boot ──────────────────────────────────────────────────────────────────────
navigate(location.pathname, false);
