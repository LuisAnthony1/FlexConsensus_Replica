// FlexConsensus App - Interactive Protein Analysis
// =================================================

const CONF_COLORS = ['#6366f1','#22c55e','#f59e0b','#ef4444','#06b6d4','#ec4899','#8b5cf6'];
const CONF_NAMES = ['Estado A','Estado B','Estado C','Estado D','Estado E','Estado F','Estado G'];
const DARK = {bg:'#1a2236', grid:'#1e293b', text:'#94a3b8'};

// Seeded PRNG for deterministic cryo-EM images
function seededRNG(seed) {
    let s = seed >>> 0;
    return function() {
        s = (s * 1664525 + 1013904223) & 0xFFFFFFFF;
        return (s >>> 0) / 0xFFFFFFFF;
    };
}

// Base URL: detecta automáticamente si está detrás de un proxy (e.g. /flexconsensus/)
const BASE_URL = window.location.pathname.replace(/\/+$/, '').replace(/\/(api|static).*$/, '') || '';

let currentProtein = null;
let currentAnalysis = null;
let proteinViewer = null;
let resultsViewer = null;
let isSpinning = false;
let isResultsSpinning = false;

// =============================================
// VIEW MANAGEMENT
// =============================================
function showView(name) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + name).classList.add('active');
    window.scrollTo(0, 0);

    const status = document.getElementById('nav-status');
    if (name === 'results' && currentProtein) {
        status.innerHTML = `<span class="dot"></span> Analisis: ${currentProtein.pdb_id}`;
    } else if (name === 'protein' && currentProtein) {
        status.innerHTML = currentProtein.pdb_id;
    } else {
        status.innerHTML = '';
    }
}

// =============================================
// 3D PROTEIN VIEWER (3Dmol.js)
// =============================================
function destroyViewer(viewerRef) {
    try { if (viewerRef) viewerRef.clear(); } catch(e) {}
}

function load3DViewer(containerId, pdbId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Destroy previous viewer if exists
    if (containerId === 'protein-viewer-3d') { destroyViewer(proteinViewer); proteinViewer = null; }
    if (containerId === 'results-viewer-3d') { destroyViewer(resultsViewer); resultsViewer = null; }

    // Fully clear container
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#64748b;font-size:.85rem;">Cargando estructura 3D...</div>';

    // Ensure container has dimensions before creating viewer
    const rect = container.getBoundingClientRect();
    if (rect.width < 10 || rect.height < 10) {
        // Container not visible yet, retry after delay
        setTimeout(() => load3DViewer(containerId, pdbId), 500);
        return;
    }

    setTimeout(() => {
        container.innerHTML = '';
        try {
            const viewer = $3Dmol.createViewer(container, {
                backgroundColor: '#0d1117',
                antialias: true,
                width: rect.width,
                height: rect.height,
            });

            if (containerId === 'protein-viewer-3d') proteinViewer = viewer;
            else if (containerId === 'results-viewer-3d') resultsViewer = viewer;

            const pdbUrl = `https://files.rcsb.org/download/${pdbId}.pdb`;
            fetch(pdbUrl).then(r => {
                if (!r.ok) throw new Error('PDB not found');
                return r.text();
            }).then(pdbData => {
                viewer.addModel(pdbData, 'pdb');
                viewer.setStyle({}, {cartoon: {color: 'spectrum'}});
                viewer.zoomTo();
                viewer.render();
                viewer.spin('y');
                setTimeout(() => { try { viewer.spin(false); } catch(e){} }, 3000);
            }).catch(() => {
                const cifUrl = `https://files.rcsb.org/download/${pdbId}.cif`;
                fetch(cifUrl).then(r => r.text()).then(cifData => {
                    viewer.addModel(cifData, 'cif');
                    viewer.setStyle({}, {cartoon: {color: 'spectrum'}});
                    viewer.zoomTo();
                    viewer.render();
                    viewer.spin('y');
                    setTimeout(() => { try { viewer.spin(false); } catch(e){} }, 3000);
                }).catch(() => {
                    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:.82rem;padding:1rem;text-align:center;">No se pudo cargar la estructura 3D.<br>Intenta con otra proteina.</div>';
                });
            });
        } catch (e) {
            container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#64748b;font-size:.82rem;">Visor 3D no disponible</div>';
        }
    }, 200);
}

function switchProteinView(mode, btnEl) {
    document.querySelectorAll('.vt-tab').forEach(t => t.classList.remove('active'));
    btnEl.classList.add('active');
    const div3d = document.getElementById('protein-viewer-3d');
    const divImg = document.getElementById('protein-viewer-img');
    if (mode === '3d') {
        div3d.style.display = '';
        divImg.style.display = 'none';
        if (proteinViewer) proteinViewer.resize();
    } else {
        div3d.style.display = 'none';
        divImg.style.display = '';
    }
}

function viewer3dStyle(style) {
    if (!proteinViewer) return;
    proteinViewer.setStyle({}, styleObj(style));
    proteinViewer.render();
}

function viewer3dSpin() {
    if (!proteinViewer) return;
    isSpinning = !isSpinning;
    proteinViewer.spin(isSpinning ? 'y' : false);
}

function resultsViewer3dStyle(style) {
    if (!resultsViewer) return;
    resultsViewer.setStyle({}, styleObj(style));
    resultsViewer.render();
}

function resultsViewerSpin() {
    if (!resultsViewer) return;
    isResultsSpinning = !isResultsSpinning;
    resultsViewer.spin(isResultsSpinning ? 'y' : false);
}

function styleObj(name) {
    switch (name) {
        case 'cartoon': return {cartoon: {color: 'spectrum'}};
        case 'stick': return {stick: {colorscheme: 'Jmol'}};
        case 'sphere': return {sphere: {colorscheme: 'Jmol', scale: 0.3}};
        case 'line': return {line: {colorscheme: 'Jmol'}};
        default: return {cartoon: {color: 'spectrum'}};
    }
}

// =============================================
// SEARCH
// =============================================
function quickSearch(term) {
    document.getElementById('search-input').value = term;
    searchProteins();
}

async function searchProteins() {
    const q = document.getElementById('search-input').value.trim();
    if (!q) return;

    const container = document.getElementById('search-results');
    container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);">Buscando en RCSB PDB...</div>';

    try {
        const resp = await fetch(`${BASE_URL}/api/search?q=${encodeURIComponent(q)}`);
        const data = await resp.json();

        if (data.error) {
            container.innerHTML = `<div style="text-align:center;padding:2rem;color:var(--red);">${data.error}</div>`;
            return;
        }

        if (data.results.length === 0) {
            container.innerHTML = '<div style="text-align:center;padding:2rem;color:var(--muted);">No se encontraron resultados. Intenta con otro termino.</div>';
            return;
        }

        let html = `<div class="sr-count">${data.total.toLocaleString()} resultados encontrados &mdash; mostrando ${data.results.length}</div>`;
        data.results.forEach(r => {
            const res = r.resolution ? `${r.resolution.toFixed(1)} A` : 'N/A';
            html += `
                <div class="sr-card" onclick="selectProtein('${r.pdb_id}')">
                    <div class="sr-pdb">${r.pdb_id}</div>
                    <div class="sr-info">
                        <div class="sr-title">${r.title || 'Sin titulo'}</div>
                        ${r.molecule ? `<div class="sr-molecule">${r.molecule}</div>` : ''}
                        <div class="sr-meta">
                            <span>${r.method || 'N/A'}</span>
                            <span>Resolucion: ${res}</span>
                            ${r.seq_length ? `<span>${r.seq_length} residuos</span>` : ''}
                            ${r.atom_count ? `<span>${r.atom_count.toLocaleString()} atomos</span>` : ''}
                        </div>
                    </div>
                    <div class="sr-arrow">&#8594;</div>
                </div>`;
        });
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = `<div style="text-align:center;padding:2rem;color:var(--red);">Error de conexion: ${err.message}</div>`;
    }
}

document.getElementById('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') searchProteins();
});

// =============================================
// PROTEIN DETAIL
// =============================================
async function selectProtein(pdbId) {
    showView('protein');
    const detail = document.getElementById('protein-detail');
    detail.style.opacity = '0.5';

    try {
        const resp = await fetch(`${BASE_URL}/api/protein/${pdbId}`);
        const p = await resp.json();
        if (p.error) throw new Error(p.error);
        currentProtein = p;

        document.getElementById('protein-img').src = p.image_url;
        document.getElementById('protein-img').onerror = function() {
            this.src = `https://cdn.rcsb.org/images/structures/${pdbId.toLowerCase()}_assembly-1.jpeg`;
        };

        // Load 3D viewer
        load3DViewer('protein-viewer-3d', pdbId);
        isSpinning = false;
        document.getElementById('protein-pdb-id').textContent = p.pdb_id;
        document.getElementById('protein-title').textContent = p.title;
        document.getElementById('protein-molecule').textContent = p.molecule || '';

        const tags = [];
        if (p.method) tags.push(p.method);
        if (p.organism) tags.push(p.organism);
        document.getElementById('protein-tags').innerHTML = tags.map(t =>
            `<span class="tag">${t}</span>`
        ).join('');

        const res = p.resolution ? `${p.resolution.toFixed(2)} A` : 'N/A';
        document.getElementById('protein-stats').innerHTML = `
            <div class="ps-item"><span class="ps-val">${res}</span><span class="ps-label">Resolucion</span></div>
            <div class="ps-item"><span class="ps-val">${(p.atom_count||0).toLocaleString()}</span><span class="ps-label">Atomos</span></div>
            <div class="ps-item"><span class="ps-val">${p.seq_length||'N/A'}</span><span class="ps-label">Residuos</span></div>
        `;

        document.getElementById('protein-links').innerHTML = `
            <a href="${p.pdb_url}" target="_blank">Ver en RCSB PDB &#8599;</a>
            <a href="${p.viewer_url}" target="_blank">Visor 3D RCSB &#8599;</a>
        `;

        detail.style.opacity = '1';
    } catch (err) {
        detail.innerHTML = `<div style="padding:3rem;text-align:center;color:var(--red);">Error cargando proteina: ${err.message}</div>`;
        detail.style.opacity = '1';
    }
}

// =============================================
// RUN ANALYSIS
// =============================================
async function runAnalysis() {
    if (!currentProtein) return;

    const btn = document.getElementById('analyze-btn');
    btn.disabled = true;
    showView('loading');

    const steps = [
        'Cargando estructura de ' + currentProtein.pdb_id + '...',
        'Simulando imagenes Cryo-EM (particulas 2D)...',
        'Ejecutando CryoDRGN (VAE en Fourier)...',
        'Ejecutando HetSIREN (SIREN en espacio real)...',
        'Alineando espacios latentes (FlexConsensus)...',
        'Calculando consensus error por particula...',
        'Ejecutando test de Mantel...',
        'Generando visualizaciones...',
    ];

    const stepsContainer = document.getElementById('loading-steps');
    stepsContainer.innerHTML = steps.map((s, i) =>
        `<div class="ls-step" id="ls-${i}"><span class="ls-check">&#9711;</span> ${s}</div>`
    ).join('');

    let stepIdx = 0;
    const stepInterval = setInterval(() => {
        if (stepIdx > 0) {
            const prev = document.getElementById(`ls-${stepIdx-1}`);
            prev.classList.remove('active');
            prev.classList.add('done');
            prev.querySelector('.ls-check').textContent = '\u2713';
        }
        if (stepIdx < steps.length) {
            const curr = document.getElementById(`ls-${stepIdx}`);
            curr.classList.add('active');
            curr.querySelector('.ls-check').textContent = '\u25CF';
            stepIdx++;
        }
    }, 400);

    try {
        const resp = await fetch(`${BASE_URL}/api/analyze`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pdb_id: currentProtein.pdb_id,
                n_particles: parseInt(document.getElementById('cfg-particles').value),
                n_methods: parseInt(document.getElementById('cfg-methods').value),
                latent_dim: parseInt(document.getElementById('cfg-latent').value),
            }),
        });
        const analysis = await resp.json();
        currentAnalysis = analysis;

        clearInterval(stepInterval);
        for (let i = 0; i < steps.length; i++) {
            const el = document.getElementById(`ls-${i}`);
            el.classList.remove('active');
            el.classList.add('done');
            el.querySelector('.ls-check').textContent = '\u2713';
        }

        await new Promise(r => setTimeout(r, 600));
        showView('results');
        renderResults(analysis);
    } catch (err) {
        clearInterval(stepInterval);
        alert('Error ejecutando analisis: ' + err.message);
        showView('protein');
    }

    btn.disabled = false;
}

// =============================================
// CRYO-EM GALLERY - Simulated projection images
// =============================================
function drawCryoEMImage(canvas, confLabel, rng) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const imgData = ctx.createImageData(w, h);
    const d = imgData.data;

    // 1. Background noise (dark, like real cryo-EM micrographs)
    for (let i = 0; i < d.length; i += 4) {
        const noise = Math.floor(rng() * 30) + 8;
        d[i] = d[i+1] = d[i+2] = noise;
        d[i+3] = 255;
    }

    // 2. CTF-like radial rings (contrast transfer function artifact)
    const cx = w/2, cy = h/2;
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const dist = Math.sqrt((x-cx)*(x-cx) + (y-cy)*(y-cy));
            const ctf = Math.sin(dist * 0.3) * 8;
            const idx = (y*w+x)*4;
            const v = Math.max(0, Math.min(255, d[idx] + ctf));
            d[idx] = d[idx+1] = d[idx+2] = v;
        }
    }

    // 3. Protein silhouette (elliptical blob - varies by conformation)
    const pcx = cx + (rng()-0.5)*16;
    const pcy = cy + (rng()-0.5)*16;
    const shapes = [
        // Different shapes per conformation to show visual difference
        {rx:22+rng()*12, ry:16+rng()*8, lobes:1},   // A: compact
        {rx:14+rng()*8, ry:26+rng()*10, lobes:2},    // B: elongated
        {rx:18+rng()*10, ry:18+rng()*10, lobes:1},   // C: round
        {rx:25+rng()*8, ry:12+rng()*6, lobes:3},     // D: wide multi-lobe
    ];
    const shape = shapes[confLabel % shapes.length];
    const angle = rng() * Math.PI;

    // Draw main body
    for (let y = 0; y < h; y++) {
        for (let x = 0; x < w; x++) {
            const dx = (x-pcx)*Math.cos(angle) + (y-pcy)*Math.sin(angle);
            const dy = -(x-pcx)*Math.sin(angle) + (y-pcy)*Math.cos(angle);
            const e = (dx*dx)/(shape.rx*shape.rx) + (dy*dy)/(shape.ry*shape.ry);
            if (e < 1.0) {
                const idx = (y*w+x)*4;
                const brightness = 35 + (1-e)*45;
                d[idx] = d[idx+1] = d[idx+2] = Math.min(255, d[idx] + brightness);
            }
        }
    }

    // Additional lobes for complex shapes
    if (shape.lobes >= 2) {
        const lx = pcx + Math.cos(angle)*shape.rx*0.5;
        const ly = pcy + Math.sin(angle)*shape.ry*0.5;
        const lr = shape.rx*0.4;
        for (let y = 0; y < h; y++) {
            for (let x = 0; x < w; x++) {
                const dist = Math.sqrt((x-lx)*(x-lx)+(y-ly)*(y-ly));
                if (dist < lr) {
                    const idx = (y*w+x)*4;
                    d[idx] = d[idx+1] = d[idx+2] = Math.min(255, d[idx] + 30*(1-dist/lr));
                }
            }
        }
    }

    ctx.putImageData(imgData, 0, 0);

    // 4. Conformation color indicator (corner dot)
    ctx.beginPath();
    ctx.arc(w-8, 8, 5, 0, Math.PI*2);
    ctx.fillStyle = CONF_COLORS[confLabel];
    ctx.fill();
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 1;
    ctx.stroke();
}

function renderCryoEMGallery(a) {
    const name = currentProtein.molecule || currentProtein.title || currentProtein.pdb_id;
    const grid = document.getElementById('cryoem-grid');
    grid.innerHTML = '';

    // Generate 20 simulated images
    const nImages = 20;
    const seed = parseInt(currentProtein.pdb_id.split('').map(c=>c.charCodeAt(0)).join('').slice(0,8)) || 12345;

    for (let i = 0; i < nImages; i++) {
        const canvas = document.createElement('canvas');
        canvas.width = 100;
        canvas.height = 100;
        const confLabel = a.labels[i % a.labels.length];
        const rng = seededRNG(seed + i*7919);
        drawCryoEMImage(canvas, confLabel, rng);
        canvas.title = `Imagen ${i+1} - ${CONF_NAMES[confLabel]}`;
        grid.appendChild(canvas);
    }

    document.getElementById('explain-cryoem').innerHTML = `
        <strong>Cada cuadrito es una "foto" simulada</strong> de ${name} congelada, vista desde un angulo diferente.<br><br>
        En la realidad, un microscopio <strong>Cryo-EM</strong> (Cryo-Electron Microscopy) congela la proteina a -196 C
        y le dispara un haz de electrones para obtener una imagen 2D en escala de grises (muy ruidosa, como las de arriba).<br><br>
        <strong>El punto de color en la esquina</strong> indica en que conformacion (pose) estaba la proteina cuando se "fotografio".
        Pero en la realidad, <strong>NO sabemos la pose de antemano</strong> &mdash; eso es lo que las IAs deben descubrir
        a partir de estas imagenes borrosas.<br><br>
        Se simularon <strong>${a.n_particles.toLocaleString()} imagenes</strong> como estas. Aqui mostramos solo 20 como ejemplo.`;

    document.getElementById('cryoem-caption').innerHTML =
        `Mostrando 20 de ${a.n_particles.toLocaleString()} imagenes simuladas.
         Cada punto de color = conformacion asignada (${a.n_conformations} poses detectadas).`;
}

// =============================================
// CHART GUIDE BOXES
// =============================================
function renderChartGuides(a) {
    const n = a.n_conformations;

    // PASO 2 guide
    let dotsHtml = '';
    for (let i = 0; i < Math.min(n, 5); i++) {
        dotsHtml += `<span class="cg-dot" style="background:${CONF_COLORS[i]}"></span> ${CONF_NAMES[i]}`;
        if (i < Math.min(n, 5)-1) dotsHtml += '<span class="cg-sep">|</span>';
    }
    document.getElementById('guide-methods').innerHTML = `
        <div class="cg-row">
            <strong>Como leer este grafico:</strong>
            Cada punto = 1 imagen de la proteina.
            Puntos cercanos = la IA cree que son poses similares.
        </div>
        <div class="cg-row">
            <strong>Colores:</strong> ${dotsHtml}
        </div>
        <div class="cg-row">
            <strong>Ejes X, Y:</strong> Coordenadas del "mapa mental" de la IA (espacio latente reducido a 2D).
            NO son coordenadas fisicas.
        </div>`;

    // PASO 3 guide
    document.getElementById('guide-consensus').innerHTML = `
        <div class="cg-row">
            <strong>Este es el mapa UNIFICADO.</strong>
            FlexConsensus tomo los dos mapas de arriba y los alinea en un solo espacio.
        </div>
        <div class="cg-row">
            <strong>"Por Conformacion":</strong> Colores = poses. Grupos bien separados = poses bien definidas.
            <span class="cg-sep">|</span>
            <strong>"Por Error":</strong> <span class="cg-dot" style="background:#22c55e"></span> verde = las 2 IAs coinciden,
            <span class="cg-dot" style="background:#ef4444"></span> rojo = discrepan.
        </div>`;

    // PASO 4 guide
    document.getElementById('guide-error').innerHTML = `
        <div class="cg-row">
            <strong>Izquierda (histograma):</strong>
            Eje X = magnitud del error. Eje Y = cuantas imagenes tienen ese error.
            <span class="cg-bar" style="background:#22c55e"></span> verde = fiable (error bajo).
            <span class="cg-bar" style="background:#ef4444"></span> rojo = dudoso (error alto).
            Linea P20 = umbral: 20% de imagenes con menor error.
        </div>
        <div class="cg-row">
            <strong>Derecha (filtrado):</strong>
            Gris = todas las ${a.n_particles.toLocaleString()} imagenes.
            Color = solo las fiables. Si los grupos de color se ven mas definidos, el filtrado funciona.
        </div>`;
}

// =============================================
// COMPARISON VISUAL (mini scatter M1 + M2 = Consensus)
// =============================================
function drawMiniScatter(canvas, data, labels) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.fillStyle = '#1a2236';
    ctx.fillRect(0, 0, w, h);

    const xArr = data.x, yArr = data.y;
    let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    for (let i = 0; i < xArr.length; i++) {
        if (xArr[i] < xMin) xMin = xArr[i];
        if (xArr[i] > xMax) xMax = xArr[i];
        if (yArr[i] < yMin) yMin = yArr[i];
        if (yArr[i] > yMax) yMax = yArr[i];
    }
    const pad = 8;
    const xRange = xMax - xMin || 1;
    const yRange = yMax - yMin || 1;

    // Draw every 3rd point for performance
    for (let i = 0; i < xArr.length; i += 3) {
        const px = pad + ((xArr[i] - xMin) / xRange) * (w - 2*pad);
        const py = pad + ((yArr[i] - yMin) / yRange) * (h - 2*pad);
        ctx.fillStyle = CONF_COLORS[labels[i]];
        ctx.globalAlpha = 0.5;
        ctx.fillRect(px, py, 2, 2);
    }
    ctx.globalAlpha = 1;
}

function renderComparisonVisual(a) {
    const container = document.getElementById('comparison-visual');
    const size = 150;

    // Create M1 mini scatter
    const c1 = document.createElement('canvas');
    c1.width = size; c1.height = size;
    drawMiniScatter(c1, a.method1, a.labels);

    // Create M2 mini scatter
    const c2 = document.createElement('canvas');
    c2.width = size; c2.height = size;
    drawMiniScatter(c2, a.method2, a.labels);

    // Create consensus mini scatter
    const c3 = document.createElement('canvas');
    c3.width = size; c3.height = size;
    drawMiniScatter(c3, a.consensus, a.labels);

    container.innerHTML = `
        <div class="cv-mini-box method1">
            <div id="cv-canvas-m1"></div>
            <div class="cv-mini-label">CryoDRGN (IA 1)</div>
        </div>
        <div class="cv-symbol">+</div>
        <div class="cv-mini-box method2">
            <div id="cv-canvas-m2"></div>
            <div class="cv-mini-label">HetSIREN (IA 2)</div>
        </div>
        <div class="cv-symbol arrow">=</div>
        <div class="cv-mini-box consensus">
            <div id="cv-canvas-cons"></div>
            <div class="cv-mini-label">Consenso Unificado</div>
        </div>`;

    document.getElementById('cv-canvas-m1').appendChild(c1);
    document.getElementById('cv-canvas-m2').appendChild(c2);
    document.getElementById('cv-canvas-cons').appendChild(c3);
}

// =============================================
// FLOW CONNECTOR LABELS
// =============================================
function renderFlowLabels(a) {
    const name = currentProtein.molecule || currentProtein.title || currentProtein.pdb_id;
    const el1 = document.getElementById('fc-label-1');
    const el2 = document.getElementById('fc-label-2');
    const el3 = document.getElementById('fc-label-3');
    if (el1) el1.textContent = `Las ${a.n_particles.toLocaleString()} imagenes pasan a 2 IAs independientes...`;
    if (el2) el2.textContent = `FlexConsensus alinea ambos mapas en uno solo...`;
    if (el3) el3.textContent = `Se mide que tan confiable es cada resultado...`;
}

// =============================================
// RENDER RESULTS
// =============================================
function renderResults(a) {
    const p = currentProtein;
    const name = p.molecule || p.title || p.pdb_id;
    const reliablePct = ((a.filtering.n_filtered / a.filtering.n_all) * 100).toFixed(1);
    const unreliablePct = (100 - parseFloat(reliablePct)).toFixed(1);

    const sorted = [...a.per_conformation].sort((x,y) => y.reliable_pct - x.reliable_pct);
    const best = sorted[0];
    const worst = sorted[sorted.length - 1];
    const dominant = a.per_conformation.reduce((a,b) => a.percentage > b.percentage ? a : b);

    const mantelQuality = a.mantel_r > 0.7 ? 'alta' : a.mantel_r > 0.5 ? 'moderada' : 'baja';
    const mantelEmoji = a.mantel_r > 0.7 ? 'good' : a.mantel_r > 0.5 ? 'warn' : 'bad';

    // Summary (no image to avoid layout overflow issues)
    document.getElementById('results-summary').innerHTML = `
        <div class="results-summary-box">
            <div class="rsb-icon">FC</div>
            <div class="rsb-info">
                <h2>${p.pdb_id} &mdash; ${name}</h2>
                <p>Analisis FlexConsensus completado. Se procesaron <strong>${a.n_particles.toLocaleString()} imagenes</strong>,
                   se detectaron <strong>${a.n_conformations} conformaciones</strong> y se comparo el consenso entre
                   <strong>${a.n_methods} metodos de IA</strong>.</p>
            </div>
        </div>`;

    // PASO 1: Proteina + visor 3D
    document.getElementById('explain-protein').innerHTML = `
        <strong>Proteina: ${name}</strong> (PDB: ${p.pdb_id})<br><br>
        <strong>Que es una proteina?</strong> Es una molecula 3D dentro de tus celulas que hace un trabajo especifico
        (como una maquina molecular). Abajo puedes ver y rotar la estructura real de <em>${name}</em>.<br><br>
        <strong>Por que cambia de forma?</strong> Las proteinas NO son rigidas. Se mueven, se abren, se cierran,
        como una mano que puede estar abierta o cerrada. Cada forma diferente se llama <strong>"conformacion"</strong>.
        Imagina que le tomas miles de fotos a una persona bailando: cada foto la captura en una pose diferente.
        Eso es exactamente lo que hace Cryo-EM: <strong>congela</strong> la proteina y le toma una "foto" 2D.<br><br>
        <strong>Que hicimos:</strong> Simulamos <strong>${a.n_particles.toLocaleString()} "fotos"</strong> de ${name}
        en diferentes poses. Dos IAs analizaran esas fotos para descubrir cuantas poses diferentes hay.`;

    // Load 3D viewer in results (with delay for DOM)
    setTimeout(() => load3DViewer('results-viewer-3d', p.pdb_id), 500);

    // Conformations explanation cards
    let confCardsHtml = `
        <div class="rpv-analogy-box">
            <h5>Que son las "conformaciones" (Estado A, B, C...)?</h5>
            <p>Imagina que ${name} es como una <strong>mano humana</strong>:<br>
            &bull; <strong>Estado A</strong> = mano abierta (palma extendida)<br>
            &bull; <strong>Estado B</strong> = mano cerrada (puno)<br>
            &bull; <strong>Estado C</strong> = mano a medio cerrar<br><br>
            Son la <strong>misma mano</strong>, pero en <strong>diferentes posiciones</strong>.
            De la misma forma, ${name} es la misma proteina pero adopta ${a.n_conformations} formas diferentes.
            FlexConsensus descubre cuantas formas existen y cuales son fiables.</p>
        </div>`;

    a.per_conformation.forEach((c, i) => {
        const color = CONF_COLORS[i];
        confCardsHtml += `
            <div class="rpv-conf-card">
                <h5><span class="conf-dot" style="background:${color}"></span>${c.name} &mdash; ${c.percentage}% de las fotos</h5>
                <p>${c.n_particles.toLocaleString()} imagenes muestran a ${name}
                en esta forma. ${c.percentage > 30 ? 'Es la pose mas comun.' :
                    c.percentage > 15 ? 'Es una pose frecuente.' :
                    'Es una pose rara.'}</p>
            </div>`;
    });

    document.getElementById('rpv-conformations-explain').innerHTML = confCardsHtml;

    // Stats
    document.getElementById('results-stats').innerHTML = `
        <div class="rs-card"><span class="rs-val">${a.n_particles.toLocaleString()}</span><span class="rs-label">Imagenes</span></div>
        <div class="rs-card"><span class="rs-val">${a.n_conformations}</span><span class="rs-label">Poses detectadas</span></div>
        <div class="rs-card"><span class="rs-val">${a.mantel_r}</span><span class="rs-label">Concordancia (Mantel r)</span></div>
        <div class="rs-card"><span class="rs-val">${reliablePct}%</span><span class="rs-label">Fiables</span></div>
    `;

    // Cryo-EM Gallery
    renderCryoEMGallery(a);

    // Flow connector labels
    renderFlowLabels(a);

    // PASO 2: Dos IAs (now 2D like the paper figures)
    document.getElementById('explain-methods').innerHTML = `
        <strong>Analogia:</strong> Le damos las ${a.n_particles.toLocaleString()} fotos de ${name} a <strong>dos doctores diferentes</strong>
        y les pedimos: "Organicen estas fotos en grupos segun la pose de la proteina".<br><br>
        <ul>
            <li><strong>CryoDRGN</strong> (izquierda): Primer "doctor". Organiza las fotos en su propio mapa.</li>
            <li><strong>HetSIREN</strong> (derecha): Segundo "doctor". Organiza las MISMAS fotos de forma diferente.</li>
        </ul>
        <strong>Cada punto</strong> = 1 foto de ${name}. <strong>Cada color</strong> = una pose diferente.
        Las etiquetas sobre el grafico indican donde esta cada grupo.
        Nota que los dos mapas se ven <strong>DIFERENTES</strong> &mdash; cada IA los organizo a su manera.`;

    // Chart guides for all sections
    renderChartGuides(a);

    // Render 2D scatter plots (like paper Figs 1-4)
    renderSubspace('chart-m1', a.method1, a.labels, 'CryoDRGN');
    renderSubspace('chart-m2', a.method2, a.labels, 'HetSIREN');

    document.getElementById('insight-methods').innerHTML = `
        <strong>Problema:</strong> Los dos mapas muestran las mismas ${a.n_particles.toLocaleString()} fotos
        pero <strong>organizadas diferente</strong>. Entonces <strong>a quien le creemos?</strong>
        FlexConsensus compara ambas opiniones y se queda solo con lo que ambos coinciden.`;

    // PASO 3: Consenso
    document.getElementById('explain-consensus').innerHTML = `
        FlexConsensus hace una <strong>"junta medica"</strong>: toma las opiniones de ambos doctores (IAs)
        y crea un <strong>mapa unificado</strong>.<br><br>
        <strong>Tres vistas:</strong>
        <ul>
            <li><strong>"Por Conformacion"</strong>: Cada color = una pose de ${name}. Grupos grandes = poses comunes.</li>
            <li><strong>"Por Error"</strong>: <span style="color:#22c55e">Verde</span> = ambas IAs coinciden (confiable).
                <span style="color:#f59e0b">Amarillo/rojo</span> = discrepan (dudoso).</li>
            <li><strong>"Subespacio"</strong>: Estilo del paper. Fondo gris = espacio comun. Colores = la vista de cada IA por separado.</li>
        </ul>`;

    // Comparison visual (mini M1 + M2 = Consensus)
    renderComparisonVisual(a);

    renderConsensus('labels');

    document.getElementById('insight-consensus').innerHTML = `
        <strong>Resultado:</strong> ${name} tiene <strong>${a.n_conformations} poses diferentes</strong>.
        La mas comun es <strong>${dominant.name}</strong> (${dominant.percentage}%).
        Usa los botones para ver la fiabilidad por error o el estilo del paper (subespacio).`;

    // PASO 4: Fiabilidad
    document.getElementById('explain-error').innerHTML = `
        <strong>Analogia:</strong> Cuando dos doctores examinan la misma radiografia, a veces coinciden y a veces no.
        El <strong>"consensus error"</strong> mide <strong>que tanto coinciden las dos IAs sobre cada foto</strong>.<br><br>
        <ul>
            <li><span style="color:#22c55e;font-weight:700">Verde</span> = ambas IAs coinciden = <strong>CONFIABLE</strong></li>
            <li><span style="color:#ef4444;font-weight:700">Rojo</span> = las IAs se contradicen = <strong>DUDOSO</strong></li>
        </ul>
        <strong>Derecha:</strong> Que pasa si nos quedamos solo con las fotos confiables (20% con menor error).
        Los grupos se definen mejor.`;

    renderHistogram(a);
    renderFiltering(a);

    document.getElementById('insight-error').innerHTML = `
        <strong>Resultado:</strong> De las ${a.n_particles.toLocaleString()} fotos,
        <span class="${parseFloat(reliablePct) > 25 ? 'good' : 'warn'}">${reliablePct}%
        (${a.filtering.n_filtered.toLocaleString()}) son confiables</span>.
        El <span class="bad">${unreliablePct}% restante son dudosas</span>.
        FlexConsensus es como una segunda opinion medica: te dice en que confiar y que descartar.`;

    // PASO 5: Tabla
    document.getElementById('explain-table').innerHTML = `
        Desglose por cada una de las <strong>${a.n_conformations} poses</strong> de ${name}.
        El <strong>"% Fiable"</strong> indica que fraccion de las imagenes de esa pose son confiables.`;

    renderTable(a);

    // CONCLUSIONES
    document.getElementById('conclusions-box').innerHTML = `
        <div class="concl-card">
            <div class="concl-icon blue">&#128300;</div>
            <div>
                <h5>${name} adopta ${a.n_conformations} poses diferentes</h5>
                <p>La pose mas comun es <strong>${dominant.name}</strong> (${dominant.percentage}%).
                   La mas rara es ${sorted[sorted.length-1].name} (${sorted[sorted.length-1].percentage}%).
                   ${name} es una proteina ${a.n_conformations > 4 ? 'muy flexible' : a.n_conformations > 2 ? 'moderadamente flexible' : 'bastante rigida'}.</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon ${mantelEmoji === 'good' ? 'green' : mantelEmoji === 'warn' ? 'yellow' : 'red'}">&#9989;</div>
            <div>
                <h5>Las dos IAs ${a.mantel_r > 0.7 ? 'coinciden mucho' : a.mantel_r > 0.5 ? 'coinciden parcialmente' : 'discrepan'} (r = ${a.mantel_r})</h5>
                <p>${a.mantel_r > 0.7
                       ? 'CryoDRGN y HetSIREN llegaron a conclusiones muy similares. Resultados confiables.'
                       : a.mantel_r > 0.5
                       ? 'Coinciden en lo general pero discrepan en detalles. Razonablemente confiable.'
                       : 'No se ponen de acuerdo. ' + name + ' es dificil de analizar.'}
                   p-valor ${a.mantel_p} confirma que no es por azar.</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon ${parseFloat(reliablePct) > 25 ? 'green' : 'yellow'}">&#128202;</div>
            <div>
                <h5>Solo el ${reliablePct}% de las fotos son confiables</h5>
                <p>De ${a.n_particles.toLocaleString()} fotos, ${a.filtering.n_filtered.toLocaleString()} son confiables.
                   Pose mas confiable: <strong>${best.name}</strong> (${best.reliable_pct}%).
                   Menos confiable: <strong>${worst.name}</strong> (${worst.reliable_pct}%).</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon blue">&#128138;</div>
            <div>
                <h5>Para que sirve esto?</h5>
                <p>Sin FlexConsensus, un cientifico no sabria que <strong>~${unreliablePct}% de sus datos son dudosos</strong>.
                   Con FlexConsensus puede descartar lo dudoso y quedarse con lo confiable.
                   Fundamental para disenar medicamentos o entender como funciona ${name}.</p>
            </div>
        </div>
    `;
}

// =============================================
// CHART HELPERS - Paper-style 2D scatter plots
// =============================================
const LAYOUT_2D = {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Inter',color:DARK.text,size:11},
    margin:{l:50,r:20,t:30,b:50},
    xaxis:{title:{text:'Dimension 1',font:{size:10}},gridcolor:DARK.grid,zerolinecolor:DARK.grid},
    yaxis:{title:{text:'Dimension 2',font:{size:10}},gridcolor:DARK.grid,zerolinecolor:DARK.grid},
    showlegend:true,
    legend:{x:0.01,y:0.99,bgcolor:'rgba(26,34,54,.85)',bordercolor:DARK.grid,borderwidth:1,font:{size:10,color:DARK.text}},
};
const PCONFIG = {displayModeBar:true,displaylogo:false,responsive:true};

// Calculate cluster centers for annotations
function clusterCenters(data, labels) {
    const centers = {};
    const counts = {};
    labels.forEach((l, i) => {
        if (!centers[l]) { centers[l] = {x:0,y:0}; counts[l] = 0; }
        centers[l].x += data.x[i];
        centers[l].y += data.y[i];
        counts[l]++;
    });
    Object.keys(centers).forEach(l => {
        centers[l].x /= counts[l];
        centers[l].y /= counts[l];
    });
    return centers;
}

// Paper-style 2D subspace plot with labeled clusters
function renderSubspace(containerId, data, labels, methodName) {
    const uniqueLabels = [...new Set(labels)].sort((a,b)=>a-b);
    const centers = clusterCenters(data, labels);

    const traces = uniqueLabels.map(label => {
        const mask = labels.map((l,i) => l===label ? i : null).filter(i => i!==null);
        return {
            type:'scatter', mode:'markers',
            name: CONF_NAMES[label],
            x: mask.map(i => data.x[i]),
            y: mask.map(i => data.y[i]),
            marker:{size:3, color:CONF_COLORS[label], opacity:.6},
            hovertemplate:`<b>${methodName} - ${CONF_NAMES[label]}</b><br>(%{x:.2f}, %{y:.2f})<extra></extra>`,
        };
    });

    // Add cluster center labels as annotations
    const annotations = uniqueLabels.map(label => ({
        x: centers[label].x,
        y: centers[label].y,
        text: `<b>${CONF_NAMES[label]}</b>`,
        showarrow: false,
        font: {size: 12, color: '#fff', family: 'Inter'},
        bgcolor: CONF_COLORS[label],
        borderpad: 4,
        bordercolor: CONF_COLORS[label],
        borderwidth: 1,
        opacity: 0.9,
    }));

    const layout = {
        ...LAYOUT_2D,
        title:{text:methodName,font:{size:13,color:DARK.text},x:0.5},
        annotations,
    };

    Plotly.newPlot(containerId, traces, layout, PCONFIG);
}

function renderConsensus(colorBy, btnEl) {
    if (!currentAnalysis) return;
    const a = currentAnalysis;

    if (btnEl) {
        document.querySelectorAll('.c-tab').forEach(t=>t.classList.remove('active'));
        btnEl.classList.add('active');
    }

    if (colorBy === 'labels') {
        // Paper Fig 3/4 style: colored by conformation
        const uniqueLabels = [...new Set(a.labels)].sort((x,y)=>x-y);
        const centers = clusterCenters(a.consensus, a.labels);

        const traces = uniqueLabels.map(label => {
            const mask = a.labels.map((l,i) => l===label ? i : null).filter(i => i!==null);
            return {
                type:'scatter', mode:'markers',
                name: CONF_NAMES[label],
                x: mask.map(i => a.consensus.x[i]),
                y: mask.map(i => a.consensus.y[i]),
                marker:{size:3.5, color:CONF_COLORS[label], opacity:.6},
                hovertemplate:`<b>${CONF_NAMES[label]}</b><br>(%{x:.2f}, %{y:.2f})<extra></extra>`,
            };
        });

        const annotations = uniqueLabels.map(label => ({
            x: centers[label].x, y: centers[label].y,
            text: `<b>${CONF_NAMES[label]}</b>`,
            showarrow: false,
            font:{size:12,color:'#fff',family:'Inter'},
            bgcolor:CONF_COLORS[label], borderpad:4, bordercolor:CONF_COLORS[label], borderwidth:1, opacity:0.9,
        }));

        Plotly.newPlot('chart-consensus', traces, {
            ...LAYOUT_2D,
            margin:{l:50,r:20,t:40,b:50},
            title:{text:'Espacio de Consenso FlexConsensus',font:{size:13,color:DARK.text},x:0.5},
            annotations,
        }, PCONFIG);

    } else if (colorBy === 'errors') {
        // Error heatmap style
        Plotly.newPlot('chart-consensus', [{
            type:'scatter', mode:'markers',
            x:a.consensus.x, y:a.consensus.y,
            marker:{
                size:3.5, color:a.errors, opacity:.7,
                colorscale:[[0,'#22c55e'],[0.3,'#06b6d4'],[0.6,'#f59e0b'],[1,'#ef4444']],
                colorbar:{title:{text:'Error',font:{size:10,color:DARK.text}},tickfont:{color:DARK.text,size:9},thickness:15,len:.6},
            },
            hovertemplate:'<b>Error: %{marker.color:.4f}</b><br>(%{x:.2f}, %{y:.2f})<extra>Verde = fiable, Rojo = dudoso</extra>',
            showlegend:false,
        }], {
            ...LAYOUT_2D,
            margin:{l:50,r:60,t:40,b:50},
            title:{text:'Consensus Error (verde=fiable, rojo=dudoso)',font:{size:13,color:DARK.text},x:0.5},
            showlegend:false,
        }, PCONFIG);

    } else if (colorBy === 'subspace') {
        // Paper style: gray common space + colored subspace per method
        const traces = [
            // Gray background - all consensus points
            {
                type:'scatter', mode:'markers',
                name:'Espacio comun (gris)',
                x:a.consensus.x, y:a.consensus.y,
                marker:{size:3, color:'#475569', opacity:.2},
                hoverinfo:'skip',
            },
            // CryoDRGN subspace colored on top
            {
                type:'scatter', mode:'markers',
                name:'CryoDRGN subespacio',
                x:a.method1.x, y:a.method1.y,
                marker:{size:3.5, color:'#6366f1', opacity:.5},
                hovertemplate:'<b>CryoDRGN</b><br>(%{x:.2f}, %{y:.2f})<extra></extra>',
            },
            // HetSIREN subspace colored on top
            {
                type:'scatter', mode:'markers',
                name:'HetSIREN subespacio',
                x:a.method2.x, y:a.method2.y,
                marker:{size:3.5, color:'#22c55e', opacity:.5},
                hovertemplate:'<b>HetSIREN</b><br>(%{x:.2f}, %{y:.2f})<extra></extra>',
            },
        ];

        Plotly.newPlot('chart-consensus', traces, {
            ...LAYOUT_2D,
            margin:{l:50,r:20,t:40,b:50},
            title:{text:'Subespacios (estilo paper Fig. 3-4)',font:{size:13,color:DARK.text},x:0.5},
        }, PCONFIG);
    }
}

function renderHistogram(a) {
    const h = a.histogram;
    const barX = h.edges.slice(0,-1).map((e,i)=>(e+h.edges[i+1])/2);
    const maxC = Math.max(...h.counts);

    Plotly.newPlot('chart-histogram', [{
        type:'bar', x:barX, y:h.counts,
        marker:{color:barX.map(x=>x<h.p20?'#22c55e':x<h.p80?'#6366f1':'#ef4444'),opacity:.85},
        hovertemplate:'<b>Error: %{x:.4f}</b><br>Imagenes: %{y:,}<extra></extra>',
    }], {
        paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
        font:{family:'Inter',color:DARK.text,size:11},
        margin:{l:55,r:20,t:20,b:55},
        xaxis:{title:{text:'Consensus Error',font:{size:11}},gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        yaxis:{title:{text:'Imagenes',font:{size:11}},gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        shapes:[
            {type:'line',x0:h.p20,x1:h.p20,y0:0,y1:maxC*1.1,line:{color:'#22c55e',width:2,dash:'dash'}},
            {type:'line',x0:h.p80,x1:h.p80,y0:0,y1:maxC*1.1,line:{color:'#ef4444',width:2,dash:'dash'}},
        ],
        annotations:[
            {x:h.p20,y:maxC*1.08,text:'<b>P20</b> Fiable',showarrow:false,font:{color:'#22c55e',size:9}},
            {x:h.p80,y:maxC*1.08,text:'<b>P80</b> No fiable',showarrow:false,font:{color:'#ef4444',size:9}},
        ],
        bargap:.02,showlegend:false,
    }, PCONFIG);
}

function renderFiltering(a) {
    const f = a.filtering;

    // Calculate centers for annotations on filtered data
    const filteredCenters = {};
    const filteredCounts = {};
    f.filtered_labels.forEach((l, i) => {
        if (!filteredCenters[l]) { filteredCenters[l] = {x:0,y:0}; filteredCounts[l] = 0; }
        filteredCenters[l].x += f.filtered_x[i];
        filteredCenters[l].y += f.filtered_y[i];
        filteredCounts[l]++;
    });
    Object.keys(filteredCenters).forEach(l => {
        filteredCenters[l].x /= filteredCounts[l];
        filteredCenters[l].y /= filteredCounts[l];
    });

    const annotations = Object.keys(filteredCenters).map(l => ({
        x: filteredCenters[l].x, y: filteredCenters[l].y,
        text: `<b>${CONF_NAMES[l]}</b>`,
        showarrow: false,
        font:{size:10,color:'#fff',family:'Inter'},
        bgcolor:CONF_COLORS[l], borderpad:3, bordercolor:CONF_COLORS[l], borderwidth:1, opacity:0.85,
    }));

    Plotly.newPlot('chart-filter', [
        {type:'scatter',mode:'markers',x:f.all_x,y:f.all_y,
         marker:{color:'#475569',size:2.5,opacity:.2},
         name:`Todas (${f.n_all.toLocaleString()})`,
         hoverinfo:'skip'},
        {type:'scatter',mode:'markers',x:f.filtered_x,y:f.filtered_y,
         marker:{color:f.filtered_labels.map(l=>CONF_COLORS[l]),size:5,opacity:.85},
         name:`Fiables (${f.n_filtered.toLocaleString()})`,
         hovertemplate:'<b>%{text}</b><br>(%{x:.2f}, %{y:.2f})<extra>Fiable</extra>',
         text:f.filtered_labels.map(l=>CONF_NAMES[l])},
    ], {
        paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
        font:{family:'Inter',color:DARK.text,size:11},
        margin:{l:55,r:20,t:20,b:55},
        xaxis:{title:'Dim 1',gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        yaxis:{title:'Dim 2',gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        legend:{x:.02,y:.98,bgcolor:'rgba(26,34,54,.9)',bordercolor:DARK.grid,borderwidth:1,font:{size:10}},
        showlegend:true,
        annotations,
    }, PCONFIG);
}

function renderTable(a) {
    let html = `<table>
        <thead><tr>
            <th>Pose</th><th>Imagenes</th><th>% del Total</th>
            <th>Error Medio</th><th>Desv. Est.</th><th>% Fiable</th><th>Fiabilidad</th>
        </tr></thead><tbody>`;

    a.per_conformation.forEach((c,i) => {
        const color = CONF_COLORS[i];
        const fColor = c.reliable_pct > 25 ? '#22c55e' : c.reliable_pct > 15 ? '#f59e0b' : '#ef4444';
        const fLabel = c.reliable_pct > 25 ? 'Alta' : c.reliable_pct > 15 ? 'Media' : 'Baja';

        html += `<tr>
            <td><span style="display:inline-block;width:12px;height:12px;border-radius:4px;background:${color};margin-right:8px;vertical-align:middle;"></span><strong>${c.name}</strong></td>
            <td>${c.n_particles.toLocaleString()}</td>
            <td>${c.percentage}%</td>
            <td>${c.error_mean}</td>
            <td>${c.error_std}</td>
            <td style="color:${fColor};font-weight:600;">${c.reliable_pct}% <span style="font-size:.7rem;opacity:.7;">${fLabel}</span></td>
            <td><div class="pbar"><div class="pbar-fill" style="width:${Math.min(c.reliable_pct*2,100)}%;background:${fColor};"></div></div></td>
        </tr>`;
    });

    html += '</tbody></table>';
    document.getElementById('results-table').innerHTML = html;
}
