// FlexConsensus App - Interactive Protein Analysis
// =================================================

const CONF_COLORS = ['#6366f1','#22c55e','#f59e0b','#ef4444','#06b6d4','#ec4899','#8b5cf6'];
const CONF_NAMES = ['Estado A','Estado B','Estado C','Estado D','Estado E','Estado F','Estado G'];
const DARK = {bg:'#1a2236', grid:'#1e293b', text:'#94a3b8'};

// Base URL: detecta automáticamente si está detrás de un proxy (e.g. /flexconsensus/)
const BASE_URL = window.location.pathname.replace(/\/+$/, '').replace(/\/(api|static).*$/, '') || '';

let currentProtein = null;
let currentAnalysis = null;
let proteinViewer = null;    // 3Dmol viewer for protein detail page
let resultsViewer = null;    // 3Dmol viewer for results page
let isSpinning = false;
let isResultsSpinning = false;

// =============================================
// VIEW MANAGEMENT
// =============================================
function showView(name) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById('view-' + name).classList.add('active');
    window.scrollTo(0, 0);

    // Update nav status
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
function load3DViewer(containerId, pdbId) {
    const container = document.getElementById(containerId);
    if (!container) return null;
    container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#64748b;font-size:.85rem;">Cargando estructura 3D...</div>';

    const viewer = $3Dmol.createViewer(container, {
        backgroundColor: '#0d1117',
        antialias: true,
    });

    const pdbUrl = `https://files.rcsb.org/download/${pdbId}.pdb`;
    fetch(pdbUrl).then(r => {
        if (!r.ok) throw new Error('PDB not found');
        return r.text();
    }).then(pdbData => {
        viewer.addModel(pdbData, 'pdb');
        viewer.setStyle({}, {cartoon: {color: 'spectrum'}});
        viewer.zoomTo();
        viewer.render();
    }).catch(() => {
        // Try mmCIF format
        const cifUrl = `https://files.rcsb.org/download/${pdbId}.cif`;
        fetch(cifUrl).then(r => r.text()).then(cifData => {
            viewer.addModel(cifData, 'cif');
            viewer.setStyle({}, {cartoon: {color: 'spectrum'}});
            viewer.zoomTo();
            viewer.render();
        }).catch(() => {
            container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;font-size:.82rem;">No se pudo cargar la estructura 3D</div>';
        });
    });

    return viewer;
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
    proteinViewer.spin(isSpinning);
}

function resultsViewer3dStyle(style) {
    if (!resultsViewer) return;
    resultsViewer.setStyle({}, styleObj(style));
    resultsViewer.render();
}

function resultsViewerSpin() {
    if (!resultsViewer) return;
    isResultsSpinning = !isResultsSpinning;
    resultsViewer.spin(isResultsSpinning);
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

// Enter key
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
        proteinViewer = load3DViewer('protein-viewer-3d', pdbId);
        isSpinning = false;
        document.getElementById('protein-pdb-id').textContent = p.pdb_id;
        document.getElementById('protein-title').textContent = p.title;
        document.getElementById('protein-molecule').textContent = p.molecule || '';

        // Tags
        const tags = [];
        if (p.method) tags.push(p.method);
        if (p.organism) tags.push(p.organism);
        document.getElementById('protein-tags').innerHTML = tags.map(t =>
            `<span class="tag">${t}</span>`
        ).join('');

        // Stats
        const res = p.resolution ? `${p.resolution.toFixed(2)} A` : 'N/A';
        document.getElementById('protein-stats').innerHTML = `
            <div class="ps-item"><span class="ps-val">${res}</span><span class="ps-label">Resolucion</span></div>
            <div class="ps-item"><span class="ps-val">${(p.atom_count||0).toLocaleString()}</span><span class="ps-label">Atomos</span></div>
            <div class="ps-item"><span class="ps-val">${p.seq_length||'N/A'}</span><span class="ps-label">Residuos</span></div>
        `;

        // Links
        document.getElementById('protein-links').innerHTML = `
            <a href="${p.pdb_url}" target="_blank">Ver en RCSB PDB &#8599;</a>
            <a href="${p.viewer_url}" target="_blank">Visor 3D &#8599;</a>
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

    // Animate loading steps
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

    // Animate steps while waiting
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

        // Finish all steps
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
// RENDER RESULTS
// =============================================
function renderResults(a) {
    const p = currentProtein;
    const name = p.molecule || p.title || p.pdb_id;
    const reliablePct = ((a.filtering.n_filtered / a.filtering.n_all) * 100).toFixed(1);
    const unreliablePct = (100 - parseFloat(reliablePct)).toFixed(1);

    // Find best and worst conformations
    const sorted = [...a.per_conformation].sort((x,y) => y.reliable_pct - x.reliable_pct);
    const best = sorted[0];
    const worst = sorted[sorted.length - 1];
    const dominant = a.per_conformation.reduce((a,b) => a.percentage > b.percentage ? a : b);

    // Mantel interpretation
    const mantelQuality = a.mantel_r > 0.7 ? 'alta' : a.mantel_r > 0.5 ? 'moderada' : 'baja';
    const mantelEmoji = a.mantel_r > 0.7 ? 'good' : a.mantel_r > 0.5 ? 'warn' : 'bad';

    // Summary
    document.getElementById('results-summary').innerHTML = `
        <div class="results-summary-box">
            <img src="${p.image_url}" onerror="this.style.display='none'">
            <div class="rsb-info">
                <h2>${p.pdb_id} &mdash; ${name}</h2>
                <p>Analisis FlexConsensus completado con exito. Se procesaron <strong>${a.n_particles.toLocaleString()} particulas</strong>,
                   se detectaron <strong>${a.n_conformations} conformaciones</strong> y se comparo el consenso entre
                   <strong>${a.n_methods} metodos de IA</strong>. Desplazate para ver los resultados paso a paso.</p>
            </div>
        </div>`;

    // PASO 1: Que proteina - con analogia clara
    document.getElementById('explain-protein').innerHTML = `
        <strong>Proteina: ${name}</strong> (PDB: ${p.pdb_id})<br><br>
        <strong>Que es una proteina?</strong> Es una molecula 3D dentro de tus celulas que hace un trabajo especifico
        (como una maquina molecular). A la izquierda puedes ver y rotar la estructura real de <em>${name}</em>.<br><br>
        <strong>Por que cambia de forma?</strong> Las proteinas NO son rigidas. Se mueven, se abren, se cierran,
        como una mano que puede estar abierta o cerrada. Cada forma diferente se llama <strong>"conformacion"</strong>.
        Imagina que le tomas miles de fotos a una persona bailando: cada foto la captura en una pose diferente.
        Eso es exactamente lo que hace Cryo-EM: <strong>congela</strong> la proteina en un instante y le toma una "foto" 2D.<br><br>
        <strong>Que hicimos:</strong> Simulamos <strong>${a.n_particles.toLocaleString()} "fotos"</strong> de ${name}
        en diferentes poses. Ahora dos IAs intentaran descubrir cuantas poses (conformaciones) diferentes hay
        y cuales son las mas comunes.`;

    // Load 3D viewer in results
    resultsViewer = load3DViewer('results-viewer-3d', p.pdb_id);
    isResultsSpinning = false;

    // Build conformations explanation cards
    let confCardsHtml = `
        <div class="rpv-analogy-box">
            <h5>Que son las "conformaciones" (Estado A, B, C...)?</h5>
            <p>Imagina que ${name} es como una <strong>mano humana</strong>:<br>
            &bull; <strong>Estado A</strong> = mano abierta (palma extendida)<br>
            &bull; <strong>Estado B</strong> = mano cerrada (puno)<br>
            &bull; <strong>Estado C</strong> = mano a medio cerrar<br><br>
            Son la <strong>misma mano</strong>, pero en <strong>diferentes posiciones</strong>.
            De la misma forma, ${name} es la misma proteina pero adopta ${a.n_conformations} formas diferentes.
            FlexConsensus descubre cuantas formas existen y cuales son fiables.<br><br>
            <strong>En los graficos 3D de abajo</strong>, cada puntito = una "foto" de ${name}.
            Los puntos del mismo color = fotos donde la proteina tenia una forma similar (misma conformacion).
            Los grupos de puntos (nubes de color) son las diferentes poses/formas.</p>
        </div>`;

    a.per_conformation.forEach((c, i) => {
        const color = CONF_COLORS[i];
        confCardsHtml += `
            <div class="rpv-conf-card">
                <h5><span class="conf-dot" style="background:${color}"></span>${c.name} &mdash; ${c.percentage}% de las fotos</h5>
                <p>${c.n_particles.toLocaleString()} de las ${a.n_particles.toLocaleString()} imagenes muestran a ${name}
                en esta forma. ${c.percentage > 30 ? 'Es la conformacion mas comun: la proteina pasa la mayor parte del tiempo en esta pose.' :
                    c.percentage > 15 ? 'Es una conformacion frecuente.' :
                    'Es una conformacion rara: la proteina adopta esta forma pocas veces.'}</p>
            </div>`;
    });

    document.getElementById('rpv-conformations-explain').innerHTML = confCardsHtml;

    // Stats
    document.getElementById('results-stats').innerHTML = `
        <div class="rs-card" title="Imagenes 2D de Cryo-EM simuladas para ${name}">
            <span class="rs-val">${a.n_particles.toLocaleString()}</span><span class="rs-label">Particulas</span></div>
        <div class="rs-card" title="Formas 3D diferentes que adopta ${name}">
            <span class="rs-val">${a.n_conformations}</span><span class="rs-label">Conformaciones</span></div>
        <div class="rs-card" title="Concordancia entre CryoDRGN y HetSIREN: ${mantelQuality}">
            <span class="rs-val">${a.mantel_r}</span><span class="rs-label">Mantel r</span></div>
        <div class="rs-card" title="p=${a.mantel_p}: la concordancia NO es por azar">
            <span class="rs-val">${a.mantel_p}</span><span class="rs-label">p-valor</span></div>
        <div class="rs-card" title="De las ${a.n_particles.toLocaleString()} particulas, solo el ${reliablePct}% tiene bajo consensus error">
            <span class="rs-val">${reliablePct}%</span><span class="rs-label">Fiables (P20)</span></div>
        <div class="rs-card" title="Se comprimieron las imagenes de ${name} en ${a.latent_dim} numeros">
            <span class="rs-val">${a.latent_dim}</span><span class="rs-label">Dim. Latente</span></div>
    `;

    // PASO 2: Dos IAs - analogia del doctor
    document.getElementById('explain-methods').innerHTML = `
        <strong>Analogia:</strong> Imagina que le das las ${a.n_particles.toLocaleString()} fotos de ${name} a <strong>dos doctores diferentes</strong>
        y les pides: "Organicen estas fotos en grupos segun la pose de la proteina".<br><br>
        <ul>
            <li><strong>CryoDRGN</strong> (izquierda): Es el primer "doctor" (una IA). Analiza las fotos a su manera
                y las organiza en un mapa 3D donde fotos de poses similares quedan juntas.</li>
            <li><strong>HetSIREN</strong> (derecha): Es el segundo "doctor" (otra IA diferente). Analiza las MISMAS fotos
                pero con otro metodo, y crea su PROPIO mapa.</li>
        </ul>
        <strong>Que ves en los graficos:</strong> Cada puntito de color = 1 foto de ${name}.
        Los puntos del mismo color = fotos donde la proteina tenia la misma pose.
        Nota que los dos mapas se ven DIFERENTES &mdash; cada IA los organizo a su manera.
        <strong>Rota</strong> arrastrando el mouse, <strong>zoom</strong> con la rueda.`;

    // Charts
    render3D('chart-m1', a.method1, a.labels, 'CryoDRGN');
    render3D('chart-m2', a.method2, a.labels, 'HetSIREN');

    document.getElementById('insight-methods').innerHTML = `
        <strong>Problema:</strong> Los dos graficos muestran las mismas ${a.n_particles.toLocaleString()} fotos
        pero <strong>organizadas de forma diferente</strong>. Es como si los dos doctores agruparan las fotos
        de formas distintas. Entonces <strong>a quien le creemos?</strong>
        Por eso existe FlexConsensus: <strong>compara ambas opiniones y se queda solo con lo que ambos doctores coinciden.</strong>`;

    // PASO 3: Consenso - analogia de la junta medica
    document.getElementById('explain-consensus').innerHTML = `
        FlexConsensus hace una <strong>"junta medica"</strong>: toma las opiniones de ambos doctores (CryoDRGN y HetSIREN)
        y crea un <strong>diagnostico unificado</strong> donde ambos estan de acuerdo.<br><br>
        <strong>Dos formas de ver el resultado:</strong>
        <ul>
            <li><strong>"Por Conformacion"</strong>: Cada color = una pose diferente de ${name}. Las nubes grandes = poses comunes.
                Las nubes chicas = poses raras que la proteina adopta pocas veces.</li>
            <li><strong>"Por Consensus Error"</strong>: Muestra <strong>donde los doctores coinciden y donde no</strong>.
                <span style="color:#22c55e">Verde oscuro</span> = ambas IAs coinciden (resultado confiable).
                <span style="color:#f59e0b">Amarillo</span> = discrepan (resultado dudoso, hay que descartarlo).</li>
        </ul>`;

    renderConsensus('labels');

    document.getElementById('insight-consensus').innerHTML = `
        <strong>Resultado:</strong> ${name} tiene <strong>${a.n_conformations} poses (conformaciones) diferentes</strong>.
        La pose mas comun es <strong>${dominant.name}</strong> &mdash; el ${dominant.percentage}% de las fotos
        (${dominant.n_particles.toLocaleString()} imagenes) muestran a la proteina en esa forma.
        <br><br>
        Haz click en <strong>"Por Consensus Error"</strong> para ver en cuales fotos los dos doctores (IAs) coinciden
        y en cuales no. Los puntos amarillos son fotos donde <strong>las IAs NO se ponen de acuerdo</strong> &mdash;
        esos resultados no son confiables y deberian descartarse.`;

    // PASO 4: Fiabilidad - analogia de segunda opinion
    document.getElementById('explain-error').innerHTML = `
        <strong>Analogia:</strong> Cuando dos doctores examinan la misma radiografia, a veces coinciden y a veces no.
        El <strong>"consensus error"</strong> mide exactamente eso: <strong>que tanto coinciden las dos IAs sobre cada foto</strong>.<br><br>
        <ul>
            <li><span style="color:#22c55e;font-weight:700">Verde</span> (error bajo) = ambas IAs dicen lo mismo = <strong>resultado CONFIABLE</strong></li>
            <li><span style="color:#ef4444;font-weight:700">Rojo</span> (error alto) = las IAs se contradicen = <strong>resultado DUDOSO, hay que descartarlo</strong></li>
        </ul>
        <strong>Grafico derecho:</strong> Muestra que pasa si nos quedamos <strong>solo con las fotos confiables</strong>
        (el 20% con menor error). Los grupos se definen mucho mejor &mdash; las poses de ${name} se distinguen con mas claridad.`;

    renderHistogram(a);
    renderFiltering(a);

    document.getElementById('insight-error').innerHTML = `
        <strong>Resultado para ${name}:</strong>
        De las ${a.n_particles.toLocaleString()} fotos, solo el <span class="${parseFloat(reliablePct) > 25 ? 'good' : 'warn'}">${reliablePct}%
        (${a.filtering.n_filtered.toLocaleString()} fotos) son confiables</span>
        (ambos "doctores" coinciden en esas). El <span class="bad">${unreliablePct}% restante son dudosas</span>.<br><br>
        <strong>Por que importa:</strong> Si un investigador usara solo UNA IA para estudiar ${name},
        <strong>no sabria que ~${unreliablePct}% de sus datos son poco confiables</strong>.
        FlexConsensus es como pedir una segunda opinion medica: te dice en que confiar y que descartar.`;

    // PASO 5: Tabla
    document.getElementById('explain-table').innerHTML = `
        Desglose por cada una de las <strong>${a.n_conformations} conformaciones</strong> de ${name}.
        El <strong>"% Fiable"</strong> indica que fraccion de las particulas de esa conformacion son confiables.
        Las conformaciones con pocas particulas (raras) suelen tener menor fiabilidad porque las IAs tienen menos datos para aprender.`;

    renderTable(a);

    // CONCLUSIONES - lenguaje simple
    document.getElementById('conclusions-box').innerHTML = `
        <div class="concl-card">
            <div class="concl-icon blue">&#128300;</div>
            <div>
                <h5>${name} adopta ${a.n_conformations} poses (formas) diferentes</h5>
                <p>Como una mano que puede estar abierta, cerrada o a medio cerrar, ${name} tiene
                   ${a.n_conformations} formas 3D diferentes. La pose mas comun es <strong>${dominant.name}</strong>
                   (${dominant.percentage}% de las fotos). La mas rara es ${sorted[sorted.length-1].name}
                   (${sorted[sorted.length-1].percentage}%). Esto significa que ${name} es una proteina
                   ${a.n_conformations > 4 ? 'muy flexible (cambia mucho de forma)' : a.n_conformations > 2 ? 'moderadamente flexible' : 'bastante rigida'}.</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon ${mantelEmoji === 'good' ? 'green' : mantelEmoji === 'warn' ? 'yellow' : 'red'}">&#9989;</div>
            <div>
                <h5>Los dos "doctores" (IAs) ${a.mantel_r > 0.7 ? 'coinciden mucho' : a.mantel_r > 0.5 ? 'coinciden parcialmente' : 'discrepan bastante'} (r = ${a.mantel_r})</h5>
                <p>${a.mantel_r > 0.7
                       ? 'CryoDRGN y HetSIREN llegaron a conclusiones MUY similares sobre ' + name + '. Esto da mucha confianza en los resultados.'
                       : a.mantel_r > 0.5
                       ? 'Las IAs coinciden en lo general pero discrepan en algunos detalles. Los resultados son razonablemente confiables.'
                       : 'Las IAs no se ponen de acuerdo, lo que sugiere que ' + name + ' es particularmente dificil de analizar.'}
                   El p-valor de ${a.mantel_p} confirma que esta coincidencia es real (no por casualidad).</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon ${parseFloat(reliablePct) > 25 ? 'green' : 'yellow'}">&#128202;</div>
            <div>
                <h5>Solo el ${reliablePct}% de las fotos son confiables</h5>
                <p>De las ${a.n_particles.toLocaleString()} fotos, solo ${a.filtering.n_filtered.toLocaleString()} son
                   resultados en los que ambas IAs coinciden. Las otras ${(a.filtering.n_all - a.filtering.n_filtered).toLocaleString()} fotos
                   deberian descartarse porque las IAs no se ponen de acuerdo.
                   La pose mas confiable es <strong>${best.name}</strong> (${best.reliable_pct}%)
                   y la menos confiable es <strong>${worst.name}</strong> (${worst.reliable_pct}%).</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon blue">&#128138;</div>
            <div>
                <h5>Para que sirve esto en la vida real?</h5>
                <p>Sin FlexConsensus, un cientifico que estudie ${name} con una sola IA <strong>no sabria que
                   ~${unreliablePct}% de sus datos son poco confiables</strong>. Es como un diagnostico medico
                   sin segunda opinion. Con FlexConsensus, puede descartar los datos dudosos y quedarse solo
                   con los confiables, obteniendo estructuras 3D mas precisas. Esto es fundamental para
                   disenar medicamentos o entender como funciona ${name} en el cuerpo.</p>
            </div>
        </div>
    `;
}

// =============================================
// CHART HELPERS
// =============================================
const LAYOUT_3D = {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Inter',color:DARK.text,size:11},
    margin:{l:0,r:0,t:10,b:0},
    scene:{
        xaxis:{gridcolor:DARK.grid,zerolinecolor:DARK.grid,title:{text:'Dim 1',font:{size:10}},backgroundcolor:DARK.bg},
        yaxis:{gridcolor:DARK.grid,zerolinecolor:DARK.grid,title:{text:'Dim 2',font:{size:10}},backgroundcolor:DARK.bg},
        zaxis:{gridcolor:DARK.grid,zerolinecolor:DARK.grid,title:{text:'Dim 3',font:{size:10}},backgroundcolor:DARK.bg},
        bgcolor:DARK.bg,
        camera:{eye:{x:1.5,y:1.5,z:1.2}},
    },
    showlegend:true,
    legend:{
        x:0.01,y:0.99,
        bgcolor:'rgba(26,34,54,.85)',
        bordercolor:DARK.grid,
        borderwidth:1,
        font:{size:11,color:DARK.text},
        itemsizing:'constant',
    },
};
const PCONFIG = {displayModeBar:true,displaylogo:false,responsive:true};

function render3D(containerId, data, labels, methodName) {
    // Separar cada conformación en un trace independiente con su leyenda
    const uniqueLabels = [...new Set(labels)].sort((a,b)=>a-b);
    const traces = uniqueLabels.map(label => {
        const mask = labels.map((l,i)=>l===label?i:null).filter(i=>i!==null);
        return {
            type:'scatter3d', mode:'markers',
            name: CONF_NAMES[label],
            x: mask.map(i=>data.x[i]),
            y: mask.map(i=>data.y[i]),
            z: mask.map(i=>data.z[i]),
            marker:{size:2.5, color:CONF_COLORS[label], opacity:.7},
            hovertemplate:`<b>${methodName} — ${CONF_NAMES[label]}</b><br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}<extra>${CONF_NAMES[label]}</extra>`,
            legendgroup: CONF_NAMES[label],
        };
    });
    Plotly.newPlot(containerId, traces, LAYOUT_3D, PCONFIG);
}

function renderConsensus(colorBy, btnEl) {
    if (!currentAnalysis) return;
    const a = currentAnalysis;

    // Update tabs
    if (btnEl) {
        document.querySelectorAll('.c-tab').forEach(t=>t.classList.remove('active'));
        btnEl.classList.add('active');
    }

    const isLabels = colorBy === 'labels';
    const consensusLayout = {...LAYOUT_3D, margin:{l:0,r:0,t:20,b:0}};

    if (isLabels) {
        // Por conformación: un trace por cada conformación con leyenda
        const uniqueLabels = [...new Set(a.labels)].sort((x,y)=>x-y);
        const traces = uniqueLabels.map(label => {
            const mask = a.labels.map((l,i)=>l===label?i:null).filter(i=>i!==null);
            return {
                type:'scatter3d', mode:'markers',
                name: CONF_NAMES[label],
                x: mask.map(i=>a.consensus.x[i]),
                y: mask.map(i=>a.consensus.y[i]),
                z: mask.map(i=>a.consensus.z[i]),
                marker:{size:2.5, color:CONF_COLORS[label], opacity:.7},
                hovertemplate:`<b>Consenso — ${CONF_NAMES[label]}</b><br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}<extra>${CONF_NAMES[label]}</extra>`,
            };
        });
        Plotly.newPlot('chart-consensus', traces, consensusLayout, PCONFIG);
    } else {
        // Por error: colorscale continua
        Plotly.newPlot('chart-consensus', [{
            type:'scatter3d', mode:'markers',
            x:a.consensus.x, y:a.consensus.y, z:a.consensus.z,
            marker:{
                size:2.5, color:a.errors, opacity:.7,
                colorscale:'Viridis',
                colorbar:{title:{text:'Error',font:{size:10,color:DARK.text}},tickfont:{color:DARK.text,size:9},thickness:15,len:.6},
            },
            hovertemplate:'<b>Error: %{marker.color:.4f}</b><br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}<extra>Bajo = fiable, Alto = dudoso</extra>',
            text:a.labels.map(l=>CONF_NAMES[l]),
            showlegend:false,
        }], {...consensusLayout, showlegend:false}, PCONFIG);
    }
}

function renderHistogram(a) {
    const h = a.histogram;
    const barX = h.edges.slice(0,-1).map((e,i)=>(e+h.edges[i+1])/2);
    const maxC = Math.max(...h.counts);

    Plotly.newPlot('chart-histogram', [{
        type:'bar', x:barX, y:h.counts,
        marker:{color:barX.map(x=>x<h.p20?'#22c55e':x<h.p80?'#6366f1':'#ef4444'),opacity:.85},
        hovertemplate:'<b>Error: %{x:.4f}</b><br>Particulas: %{y:,}<extra></extra>',
    }], {
        paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
        font:{family:'Inter',color:DARK.text,size:11},
        margin:{l:55,r:20,t:20,b:55},
        xaxis:{title:{text:'Consensus Error',font:{size:11}},gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        yaxis:{title:{text:'Particulas',font:{size:11}},gridcolor:DARK.grid,zerolinecolor:DARK.grid},
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
    Plotly.newPlot('chart-filter', [
        {type:'scatter',mode:'markers',x:f.all_x,y:f.all_y,
         marker:{color:'#475569',size:2.5,opacity:.25},
         name:`Todas (${f.n_all.toLocaleString()})`,
         hovertemplate:'Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<extra>Sin filtrar</extra>'},
        {type:'scatter',mode:'markers',x:f.filtered_x,y:f.filtered_y,
         marker:{color:f.filtered_labels.map(l=>CONF_COLORS[l]),size:5,opacity:.85},
         name:`Fiables (${f.n_filtered.toLocaleString()})`,
         hovertemplate:'<b>%{text}</b><br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<extra>Particula fiable</extra>',
         text:f.filtered_labels.map(l=>CONF_NAMES[l])},
    ], {
        paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',
        font:{family:'Inter',color:DARK.text,size:11},
        margin:{l:55,r:20,t:20,b:55},
        xaxis:{title:'Dim 1',gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        yaxis:{title:'Dim 2',gridcolor:DARK.grid,zerolinecolor:DARK.grid},
        legend:{x:.02,y:.98,bgcolor:'rgba(26,34,54,.9)',bordercolor:DARK.grid,borderwidth:1,font:{size:11}},
        showlegend:true,
    }, PCONFIG);
}

function renderTable(a) {
    let html = `<table>
        <thead><tr>
            <th>Conformacion</th><th>Particulas</th><th>% del Total</th>
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
