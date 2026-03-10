// FlexConsensus - Interactive Charts
// ===================================

const COLORS = {
    bg: '#1a2236',
    grid: '#1e293b',
    text: '#94a3b8',
    textLight: '#f1f5f9',
    accent: '#6366f1',
    accentLight: '#818cf8',
    conformations: ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4'],
    confNames: ['Abierta', 'Semi-abierta', 'Cerrada', 'Intermedia A', 'Intermedia B'],
};

const LAYOUT_3D = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: 'Inter', color: COLORS.text, size: 11 },
    margin: { l: 0, r: 0, t: 10, b: 0 },
    scene: {
        xaxis: {
            gridcolor: COLORS.grid, zerolinecolor: COLORS.grid,
            title: { text: 'Dimension 1', font: { size: 10 } },
            backgroundcolor: COLORS.bg,
        },
        yaxis: {
            gridcolor: COLORS.grid, zerolinecolor: COLORS.grid,
            title: { text: 'Dimension 2', font: { size: 10 } },
            backgroundcolor: COLORS.bg,
        },
        zaxis: {
            gridcolor: COLORS.grid, zerolinecolor: COLORS.grid,
            title: { text: 'Dimension 3', font: { size: 10 } },
            backgroundcolor: COLORS.bg,
        },
        bgcolor: COLORS.bg,
        camera: {
            eye: { x: 1.5, y: 1.5, z: 1.2 },
        },
    },
    showlegend: false,
};

const CONFIG = {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['sendDataToCloud'],
    responsive: true,
};

// Cache for loaded data
let consensusData = null;

// --- HELPERS ---

async function fetchJSON(url) {
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    } catch (err) {
        console.error(`Error cargando ${url}:`, err);
        return null;
    }
}

function showError(containerId, msg) {
    const el = document.getElementById(containerId);
    if (el) {
        el.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;
            height:300px;color:#ef4444;font-size:0.9rem;">Error: ${msg}</div>`;
    }
}

function make3DScatter(data, colorBy) {
    const isLabels = colorBy === 'labels';
    const colors = isLabels
        ? data.labels.map(l => COLORS.conformations[l])
        : data.errors;

    return [{
        type: 'scatter3d',
        mode: 'markers',
        x: data.x,
        y: data.y,
        z: data.z,
        marker: {
            size: 2.5,
            color: colors,
            colorscale: isLabels ? undefined : 'Viridis',
            opacity: 0.7,
            ...(!isLabels ? {
                colorbar: {
                    title: { text: 'Consensus\nError', font: { size: 10, color: COLORS.text } },
                    tickfont: { color: COLORS.text, size: 9 },
                    thickness: 15,
                    len: 0.6,
                },
            } : {}),
        },
        hovertemplate: isLabels
            ? '<b>Conformacion: %{text}</b><br>' +
              'Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}' +
              '<extra>Cada punto = 1 particula (imagen 2D de la proteina)</extra>'
            : '<b>Consensus Error: %{marker.color:.4f}</b><br>' +
              'Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}' +
              '<extra>Bajo error = alta fiabilidad entre metodos</extra>',
        text: data.labels.map(l => `${COLORS.confNames[l]} (${l + 1})`),
    }];
}

// --- INIT CHARTS ---

async function initLatentSpaces() {
    const [cryodrgn, hetsiren] = await Promise.all([
        fetchJSON('/api/latent/cryodrgn'),
        fetchJSON('/api/latent/hetsiren'),
    ]);

    if (!cryodrgn) { showError('chart-cryodrgn', 'No se pudieron cargar datos'); return; }
    if (!hetsiren) { showError('chart-hetsiren', 'No se pudieron cargar datos'); return; }

    Plotly.newPlot('chart-cryodrgn', make3DScatter(cryodrgn, 'labels'), LAYOUT_3D, CONFIG);
    Plotly.newPlot('chart-hetsiren', make3DScatter(hetsiren, 'labels'), LAYOUT_3D, CONFIG);
}

async function initConsensus() {
    consensusData = await fetchJSON('/api/latent/consensus');
    if (!consensusData) { showError('chart-consensus', 'No se pudieron cargar datos'); return; }

    Plotly.newPlot('chart-consensus', make3DScatter(consensusData, 'labels'), {
        ...LAYOUT_3D,
        margin: { l: 0, r: 0, t: 20, b: 0 },
    }, CONFIG);
}

function showConsensus(colorBy) {
    if (!consensusData) return;

    // Update tabs - use closest to handle clicks on child elements
    document.querySelectorAll('.method-tab').forEach(tab => tab.classList.remove('active'));
    const btn = event.target.closest('.method-tab');
    if (btn) btn.classList.add('active');

    Plotly.react('chart-consensus', make3DScatter(consensusData, colorBy), {
        ...LAYOUT_3D,
        margin: { l: 0, r: 0, t: 20, b: 0 },
    }, CONFIG);
}

async function initErrorHistogram() {
    const data = await fetchJSON('/api/errors');
    if (!data) { showError('chart-errors', 'No se pudieron cargar datos'); return; }

    const barX = data.edges.slice(0, -1).map((e, i) => (e + data.edges[i + 1]) / 2);
    const maxCount = Math.max(...data.counts);

    const traces = [
        {
            type: 'bar',
            x: barX,
            y: data.counts,
            marker: {
                color: barX.map(x => x < data.percentile_20 ? '#22c55e' :
                    x < data.percentile_80 ? '#6366f1' : '#ef4444'),
                opacity: 0.85,
            },
            hovertemplate:
                '<b>Consensus Error: %{x:.4f}</b><br>' +
                'Particulas: %{y:,}<br>' +
                '<extra>Cada barra = rango de error</extra>',
        },
    ];

    const shapes = [
        {
            type: 'line', x0: data.percentile_20, x1: data.percentile_20,
            y0: 0, y1: maxCount * 1.1,
            line: { color: '#22c55e', width: 2, dash: 'dash' },
        },
        {
            type: 'line', x0: data.percentile_80, x1: data.percentile_80,
            y0: 0, y1: maxCount * 1.1,
            line: { color: '#ef4444', width: 2, dash: 'dash' },
        },
        {
            type: 'line', x0: data.median, x1: data.median,
            y0: 0, y1: maxCount * 0.9,
            line: { color: '#f59e0b', width: 1.5, dash: 'dot' },
        },
    ];

    const annotations = [
        {
            x: data.percentile_20, y: maxCount * 1.08,
            text: '<b>P20</b><br>Umbral fiable', showarrow: false,
            font: { color: '#22c55e', size: 9 }, align: 'center',
        },
        {
            x: data.percentile_80, y: maxCount * 1.08,
            text: '<b>P80</b><br>Umbral no fiable', showarrow: false,
            font: { color: '#ef4444', size: 9 }, align: 'center',
        },
        {
            x: data.median, y: maxCount * 0.85,
            text: `Mediana: ${data.median.toFixed(4)}`, showarrow: false,
            font: { color: '#f59e0b', size: 9 },
        },
    ];

    Plotly.newPlot('chart-errors', traces, {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter', color: COLORS.text, size: 11 },
        margin: { l: 55, r: 20, t: 30, b: 55 },
        xaxis: {
            title: { text: 'Consensus Error (menor = mas fiable)', font: { size: 11 } },
            gridcolor: COLORS.grid,
            zerolinecolor: COLORS.grid,
        },
        yaxis: {
            title: { text: 'Numero de Particulas', font: { size: 11 } },
            gridcolor: COLORS.grid,
            zerolinecolor: COLORS.grid,
        },
        shapes, annotations,
        bargap: 0.02,
        showlegend: false,
    }, CONFIG);
}

async function initFiltering() {
    const data = await fetchJSON('/api/filtering');
    if (!data) { showError('chart-filtering', 'No se pudieron cargar datos'); return; }

    const traces = [
        {
            type: 'scatter',
            mode: 'markers',
            x: data.all.x,
            y: data.all.y,
            marker: { color: '#475569', size: 2.5, opacity: 0.25 },
            name: `Todas las particulas (${data.n_all.toLocaleString()})`,
            hovertemplate:
                'Dim1: %{x:.2f}<br>Dim2: %{y:.2f}' +
                '<extra>Particula sin filtrar - puede ser fiable o no</extra>',
        },
        {
            type: 'scatter',
            mode: 'markers',
            x: data.filtered.x,
            y: data.filtered.y,
            marker: {
                color: data.filtered.labels.map(l => COLORS.conformations[l]),
                size: 5,
                opacity: 0.85,
            },
            name: `Solo fiables (${data.n_filtered.toLocaleString()})`,
            hovertemplate:
                '<b>Conformacion: %{text}</b><br>' +
                'Dim1: %{x:.2f}<br>Dim2: %{y:.2f}' +
                '<extra>Particula fiable - ambos metodos coinciden</extra>',
            text: data.filtered.labels.map(l => `${COLORS.confNames[l]}`),
        },
    ];

    Plotly.newPlot('chart-filtering', traces, {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter', color: COLORS.text, size: 11 },
        margin: { l: 55, r: 20, t: 20, b: 55 },
        xaxis: {
            title: { text: 'Dimension 1', font: { size: 11 } },
            gridcolor: COLORS.grid,
            zerolinecolor: COLORS.grid,
        },
        yaxis: {
            title: { text: 'Dimension 2', font: { size: 11 } },
            gridcolor: COLORS.grid,
            zerolinecolor: COLORS.grid,
        },
        legend: {
            x: 0.02, y: 0.98,
            bgcolor: 'rgba(26,34,54,0.9)',
            bordercolor: COLORS.grid,
            borderwidth: 1,
            font: { size: 11 },
        },
        showlegend: true,
    }, CONFIG);
}

async function initMetricsTable() {
    const data = await fetchJSON('/api/metrics');
    if (!data) return;

    const tbody = document.getElementById('metrics-table');

    data.per_conformation.forEach(conf => {
        const fiabilityColor = conf.porcentaje_fiable > 25 ? '#22c55e' :
            conf.porcentaje_fiable > 15 ? '#f59e0b' : '#ef4444';
        const fiabilityLabel = conf.porcentaje_fiable > 25 ? 'Alta' :
            conf.porcentaje_fiable > 15 ? 'Media' : 'Baja';

        const row = document.createElement('tr');
        row.title = `Conformacion ${COLORS.confNames[conf.conformacion - 1]}: ${conf.n_particulas.toLocaleString()} particulas con error medio de ${conf.error_medio.toFixed(4)}`;
        row.innerHTML = `
            <td>
                <span style="display:inline-block;width:12px;height:12px;border-radius:4px;
                    background:${COLORS.conformations[conf.conformacion - 1]};margin-right:8px;vertical-align:middle;"></span>
                <strong>${COLORS.confNames[conf.conformacion - 1]}</strong>
                <span style="color:${COLORS.text};font-size:0.75rem;"> (Estado ${conf.conformacion})</span>
            </td>
            <td>${conf.n_particulas.toLocaleString()}</td>
            <td>${conf.error_medio.toFixed(4)}</td>
            <td>${conf.error_std.toFixed(4)}</td>
            <td style="color:${fiabilityColor};font-weight:600;">
                ${conf.porcentaje_fiable.toFixed(1)}%
                <span style="font-size:0.7rem;font-weight:400;opacity:0.7;"> ${fiabilityLabel}</span>
            </td>
            <td>
                <div class="progress-bar" title="${fiabilityLabel} fiabilidad: ${conf.porcentaje_fiable.toFixed(1)}% de particulas son confiables">
                    <div class="fill" style="width:${Math.min(conf.porcentaje_fiable * 2, 100)}%;background:${fiabilityColor};"></div>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// --- BOOT ---
document.addEventListener('DOMContentLoaded', () => {
    // Init all charts - they handle their own loading states via innerHTML replacement
    initLatentSpaces();
    initConsensus();
    initErrorHistogram();
    initFiltering();
    initMetricsTable();
});

// Smooth scroll for nav with offset for fixed navbar
document.querySelectorAll('.nav-links a').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-links a').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        const target = document.querySelector(link.getAttribute('href'));
        if (target) {
            const offset = 80; // navbar height
            const y = target.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({ top: y, behavior: 'smooth' });
        }
    });
});

// Update active nav link on scroll
window.addEventListener('scroll', () => {
    const sections = document.querySelectorAll('.section, .hero, .stats-row');
    const links = document.querySelectorAll('.nav-links a');
    let current = '';

    sections.forEach(section => {
        const rect = section.getBoundingClientRect();
        if (rect.top <= 120) {
            current = section.id || '';
        }
    });

    if (current) {
        links.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) {
                link.classList.add('active');
            }
        });
    }
});
