// FlexConsensus - Interactive Charts (Paper-Style KDE)
// =====================================================

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

// Paper-style KDE colorscale: black (empty) → dark blue → green → yellow (dense)
const KDE_COLORSCALE = [
    [0.0,  '#0a0e1a'],
    [0.08, '#0d1b3e'],
    [0.20, '#0f2a5a'],
    [0.35, '#0e4a6e'],
    [0.50, '#0e6b6e'],
    [0.65, '#0f8c50'],
    [0.80, '#22c55e'],
    [0.92, '#7add40'],
    [1.0,  '#fde725'],
];

// 2D KDE layout (replaces the old LAYOUT_3D)
const LAYOUT_KDE = {
    paper_bgcolor: '#0a0e1a',
    plot_bgcolor:  '#0a0e1a',
    font: { family: 'Inter', color: '#94a3b8', size: 10 },
    margin: { l: 50, r: 20, t: 35, b: 50 },
    xaxis: {
        title: { text: 'Dimension 1', font: { size: 10 } },
        gridcolor: '#1a2236', zerolinecolor: '#1e293b',
        color: '#64748b', tickfont: { size: 9 },
    },
    yaxis: {
        title: { text: 'Dimension 2', font: { size: 10 } },
        gridcolor: '#1a2236', zerolinecolor: '#1e293b',
        color: '#64748b', tickfont: { size: 9 },
    },
    showlegend: true,
    legend: {
        x: 0.01, y: 0.99,
        bgcolor: 'rgba(10,14,26,0.9)',
        bordercolor: '#1e293b', borderwidth: 1,
        font: { size: 9, color: '#94a3b8' },
    },
};

const CONFIG = {
    displayModeBar: true,
    displaylogo: false,
    modeBarButtonsToRemove: ['sendDataToCloud'],
    responsive: true,
};

// Cache
let consensusData = null;
let filteringData = null;

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

// Build KDE-style traces (paper figure look)
// Returns: [kde_contour_trace, ...scatter_traces]
function makeKDETraces(data, colorBy, title) {
    const traces = [];

    // Layer 1: KDE density background (the "landscape" look from paper)
    traces.push({
        type: 'histogram2dcontour',
        x: data.x, y: data.y,
        colorscale: KDE_COLORSCALE,
        showscale: false,
        ncontours: 18,
        contours: { coloring: 'heatmap', showlines: false },
        nbinsx: 55, nbinsy: 55,
        opacity: 1.0,
        hoverinfo: 'skip',
        showlegend: false,
        name: 'Densidad',
    });

    if (colorBy === 'labels') {
        // Layer 2: scatter colored by conformation
        const uniqueLabels = [...new Set(data.labels)].sort((a, b) => a - b);
        uniqueLabels.forEach(label => {
            const idx = data.labels.map((l, i) => l === label ? i : null).filter(i => i !== null);
            traces.push({
                type: 'scatter', mode: 'markers',
                name: COLORS.confNames[label],
                x: idx.map(i => data.x[i]),
                y: idx.map(i => data.y[i]),
                marker: { color: COLORS.conformations[label], size: 2.5, opacity: 0.55 },
                hovertemplate: `<b>${COLORS.confNames[label]}</b><br>(%{x:.2f}, %{y:.2f})<extra></extra>`,
            });
        });
    } else if (colorBy === 'errors') {
        traces.push({
            type: 'scatter', mode: 'markers',
            x: data.x, y: data.y,
            marker: {
                color: data.errors, size: 2.5, opacity: 0.65,
                colorscale: [[0,'#22c55e'],[0.35,'#06b6d4'],[0.65,'#f59e0b'],[1,'#ef4444']],
                colorbar: {
                    title: { text: 'Error', font: { size: 9, color: '#94a3b8' } },
                    tickfont: { color: '#94a3b8', size: 8 },
                    thickness: 12, len: 0.6,
                },
            },
            hovertemplate: '<b>Error: %{marker.color:.4f}</b><br>(%{x:.2f}, %{y:.2f})<extra>Verde=fiable Rojo=dudoso</extra>',
            showlegend: false,
        });
    }

    return traces;
}

// Build side-by-side subplots: Full space (left) | Significant space (right)
// Mimics paper Figs 1 and 2
function makeFullVsSignificantTraces(consData, filtData) {
    const allX = consData.x, allY = consData.y;
    const filtX = filtData.filtered.x, filtY = filtData.filtered.y;
    const filtLabels = filtData.filtered.labels;

    return {
        traces: [
            // Left subplot: Full consensus space (KDE)
            { type: 'histogram2dcontour', x: allX, y: allY,
              colorscale: KDE_COLORSCALE, showscale: false, ncontours: 18,
              contours: { coloring: 'heatmap', showlines: false },
              nbinsx: 55, nbinsy: 55, opacity: 1.0,
              hoverinfo: 'skip', showlegend: false, xaxis: 'x', yaxis: 'y' },
            // Left subplot: conformation scatter (all, semi-transparent)
            { type: 'scatter', mode: 'markers', name: 'Completo',
              x: allX.filter((_, i) => i % 4 === 0),
              y: allY.filter((_, i) => i % 4 === 0),
              marker: { color: '#ec4899', size: 1.5, opacity: 0.25 },
              showlegend: false, xaxis: 'x', yaxis: 'y', hoverinfo: 'skip' },

            // Right subplot: Significant consensus space (KDE)
            { type: 'histogram2dcontour', x: filtX, y: filtY,
              colorscale: KDE_COLORSCALE, showscale: false, ncontours: 18,
              contours: { coloring: 'heatmap', showlines: false },
              nbinsx: 55, nbinsy: 55, opacity: 1.0,
              hoverinfo: 'skip', showlegend: false, xaxis: 'x2', yaxis: 'y2' },
            // Right subplot: filtered scatter colored by conformation
            { type: 'scatter', mode: 'markers', name: 'Significativo',
              x: filtX, y: filtY,
              marker: {
                color: filtLabels.map(l => COLORS.conformations[l]),
                size: 3, opacity: 0.65,
              },
              showlegend: false, xaxis: 'x2', yaxis: 'y2',
              hovertemplate: '<b>%{text}</b><br>(%{x:.2f}, %{y:.2f})<extra>Particula fiable</extra>',
              text: filtLabels.map(l => COLORS.confNames[l]) },
        ],
        layout: {
            paper_bgcolor: '#0a0e1a', plot_bgcolor: '#0a0e1a',
            font: { family: 'Inter', color: '#94a3b8', size: 10 },
            margin: { l: 50, r: 30, t: 50, b: 50 },
            grid: { rows: 1, columns: 2, pattern: 'independent', xgap: 0.08 },
            xaxis:  { title: { text: 'Dim 1' }, gridcolor: '#1a2236', zerolinecolor: '#1e293b', tickfont: { size: 9 }, color: '#64748b' },
            yaxis:  { title: { text: 'Dim 2' }, gridcolor: '#1a2236', zerolinecolor: '#1e293b', tickfont: { size: 9 }, color: '#64748b' },
            xaxis2: { title: { text: 'Dim 1' }, gridcolor: '#1a2236', zerolinecolor: '#1e293b', tickfont: { size: 9 }, color: '#64748b' },
            yaxis2: { title: { text: 'Dim 2' }, gridcolor: '#1a2236', zerolinecolor: '#1e293b', tickfont: { size: 9 }, color: '#64748b' },
            annotations: [
                { text: '<b>Full consensus space</b>', font: { color: '#f1f5f9', size: 12 },
                  x: 0.22, y: 1.05, xref: 'paper', yref: 'paper', showarrow: false },
                { text: '<b>Significant consensus space</b>', font: { color: '#22c55e', size: 12 },
                  x: 0.78, y: 1.05, xref: 'paper', yref: 'paper', showarrow: false },
            ],
            showlegend: false,
        },
    };
}

// --- INIT CHARTS ---

async function initLatentSpaces() {
    const [cryodrgn, hetsiren] = await Promise.all([
        fetchJSON('/api/latent/cryodrgn'),
        fetchJSON('/api/latent/hetsiren'),
    ]);

    if (!cryodrgn) { showError('chart-cryodrgn', 'No se pudieron cargar datos'); return; }
    if (!hetsiren) { showError('chart-hetsiren', 'No se pudieron cargar datos'); return; }

    const layout = {
        ...LAYOUT_KDE,
        showlegend: true,
        legend: { x: 0.01, y: 0.99, bgcolor: 'rgba(10,14,26,0.9)', bordercolor: '#1e293b', borderwidth: 1, font: { size: 9, color: '#94a3b8' } },
    };

    Plotly.newPlot('chart-cryodrgn',
        makeKDETraces(cryodrgn, 'labels', 'CryoDRGN'),
        { ...layout, title: { text: 'CryoDRGN &mdash; Full Consensus Landscape', font: { size: 12, color: '#f1f5f9' }, x: 0.5 } },
        CONFIG
    );
    Plotly.newPlot('chart-hetsiren',
        makeKDETraces(hetsiren, 'labels', 'HetSIREN'),
        { ...layout, title: { text: 'HetSIREN &mdash; Full Consensus Landscape', font: { size: 12, color: '#f1f5f9' }, x: 0.5 } },
        CONFIG
    );
}

async function initConsensus() {
    [consensusData, filteringData] = await Promise.all([
        fetchJSON('/api/latent/consensus'),
        fetchJSON('/api/filtering'),
    ]);
    if (!consensusData) { showError('chart-consensus', 'No se pudieron cargar datos'); return; }

    // Default view: by conformation (paper style)
    Plotly.newPlot('chart-consensus',
        makeKDETraces(consensusData, 'labels'),
        { ...LAYOUT_KDE, title: { text: 'Common Consensus Landscape', font: { size: 12, color: '#f1f5f9' }, x: 0.5 }, margin: { l: 50, r: 20, t: 45, b: 50 } },
        CONFIG
    );
}

function showConsensus(colorBy) {
    if (!consensusData) return;

    document.querySelectorAll('.method-tab').forEach(tab => tab.classList.remove('active'));
    const btn = event.target.closest('.method-tab');
    if (btn) btn.classList.add('active');

    if (colorBy === 'paper') {
        // Paper Fig style: full vs significant side by side
        if (!filteringData) { fetchJSON('/api/filtering').then(d => { filteringData = d; showConsensus('paper'); }); return; }
        const { traces, layout } = makeFullVsSignificantTraces(consensusData, filteringData);
        Plotly.react('chart-consensus', traces, layout, CONFIG);
        return;
    }

    const title = colorBy === 'labels'
        ? 'Common Consensus Landscape'
        : 'Consensus Error Landscape';

    Plotly.react('chart-consensus',
        makeKDETraces(consensusData, colorBy),
        { ...LAYOUT_KDE, title: { text: title, font: { size: 12, color: '#f1f5f9' }, x: 0.5 }, margin: { l: 50, r: colorBy === 'errors' ? 70 : 20, t: 45, b: 50 } },
        CONFIG
    );
}

async function initErrorHistogram() {
    const data = await fetchJSON('/api/errors');
    if (!data) { showError('chart-errors', 'No se pudieron cargar datos'); return; }

    const barX = data.edges.slice(0, -1).map((e, i) => (e + data.edges[i + 1]) / 2);
    const maxCount = Math.max(...data.counts);

    Plotly.newPlot('chart-errors', [{
        type: 'bar', x: barX, y: data.counts,
        marker: {
            color: barX.map(x => x < data.percentile_20 ? '#22c55e' :
                x < data.percentile_80 ? '#6366f1' : '#ef4444'),
            opacity: 0.85,
        },
        hovertemplate: '<b>Consensus Error: %{x:.4f}</b><br>Particulas: %{y:,}<extra></extra>',
        name: 'Consensus Error',
    }], {
        paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)',
        font: { family: 'Inter', color: COLORS.text, size: 11 },
        margin: { l: 55, r: 20, t: 30, b: 55 },
        xaxis: { title: { text: 'Consensus Error (menor = mas fiable)', font: { size: 11 } }, gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
        yaxis: { title: { text: 'Numero de Particulas', font: { size: 11 } }, gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
        bargap: 0.02,
        showlegend: false,
        shapes: [
            { type: 'line', x0: data.percentile_20, x1: data.percentile_20, y0: 0, y1: maxCount * 1.1, line: { color: '#22c55e', width: 2, dash: 'dash' } },
            { type: 'line', x0: data.percentile_80, x1: data.percentile_80, y0: 0, y1: maxCount * 1.1, line: { color: '#ef4444', width: 2, dash: 'dash' } },
            { type: 'line', x0: data.median, x1: data.median, y0: 0, y1: maxCount * 0.9, line: { color: '#f59e0b', width: 1.5, dash: 'dot' } },
        ],
        annotations: [
            { x: data.percentile_20, y: maxCount * 1.08, text: '<b>P20</b><br>Umbral fiable', showarrow: false, font: { color: '#22c55e', size: 9 }, align: 'center' },
            { x: data.percentile_80, y: maxCount * 1.08, text: '<b>P80</b><br>No fiable', showarrow: false, font: { color: '#ef4444', size: 9 }, align: 'center' },
            { x: data.median, y: maxCount * 0.85, text: `Mediana: ${data.median.toFixed(4)}`, showarrow: false, font: { color: '#f59e0b', size: 9 } },
        ],
    }, CONFIG);
}

async function initFiltering() {
    const data = await fetchJSON('/api/filtering');
    if (!data) { showError('chart-filtering', 'No se pudieron cargar datos'); return; }
    filteringData = data;

    // Paper style: gray KDE background (all particles) + colored significant on top
    const traces = [
        // KDE of all particles (gray-tinted)
        { type: 'histogram2dcontour',
          x: data.all.x, y: data.all.y,
          colorscale: [[0,'#0a0e1a'],[0.3,'#1a2a3a'],[0.7,'#2e4a5a'],[1,'#3b6678']],
          showscale: false, ncontours: 14, contours: { coloring: 'heatmap', showlines: false },
          nbinsx: 55, nbinsy: 55, opacity: 0.9,
          hoverinfo: 'skip', showlegend: false },
        // Colored significant particles on top
        { type: 'scatter', mode: 'markers',
          x: data.filtered.x, y: data.filtered.y,
          marker: {
            color: data.filtered.labels.map(l => COLORS.conformations[l]),
            size: 4, opacity: 0.8,
          },
          name: `Significativas (${data.n_filtered.toLocaleString()})`,
          hovertemplate: '<b>%{text}</b><br>(%{x:.2f}, %{y:.2f})<extra>Particula fiable</extra>',
          text: data.filtered.labels.map(l => COLORS.confNames[l]),
        },
    ];

    Plotly.newPlot('chart-filtering', traces, {
        paper_bgcolor: '#0a0e1a', plot_bgcolor: '#0a0e1a',
        font: { family: 'Inter', color: COLORS.text, size: 11 },
        margin: { l: 55, r: 20, t: 20, b: 55 },
        xaxis: { title: { text: 'Dimension 1', font: { size: 11 } }, gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: '#64748b' },
        yaxis: { title: { text: 'Dimension 2', font: { size: 11 } }, gridcolor: COLORS.grid, zerolinecolor: COLORS.grid, color: '#64748b' },
        legend: { x: 0.02, y: 0.98, bgcolor: 'rgba(10,14,26,0.9)', bordercolor: COLORS.grid, borderwidth: 1, font: { size: 10 } },
        showlegend: true,
        annotations: [{
            x: 0.5, y: 1.03, xref: 'paper', yref: 'paper',
            text: '<b>Significant consensus space</b>',
            showarrow: false, font: { color: '#22c55e', size: 11 },
        }],
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
                <div class="progress-bar" title="${fiabilityLabel} fiabilidad: ${conf.porcentaje_fiable.toFixed(1)}%">
                    <div class="fill" style="width:${Math.min(conf.porcentaje_fiable * 2, 100)}%;background:${fiabilityColor};"></div>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// --- BOOT ---
document.addEventListener('DOMContentLoaded', () => {
    initLatentSpaces();
    initConsensus();
    initErrorHistogram();
    initFiltering();
    initMetricsTable();
});

// Smooth scroll + active nav
document.querySelectorAll('.nav-links a').forEach(link => {
    link.addEventListener('click', e => {
        e.preventDefault();
        document.querySelectorAll('.nav-links a').forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        const target = document.querySelector(link.getAttribute('href'));
        if (target) {
            const y = target.getBoundingClientRect().top + window.pageYOffset - 80;
            window.scrollTo({ top: y, behavior: 'smooth' });
        }
    });
});

window.addEventListener('scroll', () => {
    const sections = document.querySelectorAll('.section, .hero, .stats-row');
    const links = document.querySelectorAll('.nav-links a');
    let current = '';
    sections.forEach(section => {
        if (section.getBoundingClientRect().top <= 120) current = section.id || '';
    });
    if (current) {
        links.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href') === `#${current}`) link.classList.add('active');
        });
    }
});
