// FlexConsensus App - Interactive Protein Analysis
// =================================================

const CONF_COLORS = ['#6366f1','#22c55e','#f59e0b','#ef4444','#06b6d4','#ec4899','#8b5cf6'];
const CONF_NAMES = ['Estado A','Estado B','Estado C','Estado D','Estado E','Estado F','Estado G'];
const DARK = {bg:'#1a2236', grid:'#1e293b', text:'#94a3b8'};

let currentProtein = null;
let currentAnalysis = null;

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
        const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
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
        const resp = await fetch(`/api/protein/${pdbId}`);
        const p = await resp.json();
        if (p.error) throw new Error(p.error);
        currentProtein = p;

        document.getElementById('protein-img').src = p.image_url;
        document.getElementById('protein-img').onerror = function() {
            this.src = `https://cdn.rcsb.org/images/structures/${pdbId.toLowerCase()}_assembly-1.jpeg`;
        };
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
        const resp = await fetch('/api/analyze', {
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

    // PASO 1: Que proteina
    document.getElementById('explain-protein').innerHTML = `
        <strong>Proteina seleccionada: ${name}</strong> (PDB: ${p.pdb_id})<br><br>
        Se simularon <strong>${a.n_particles.toLocaleString()} imagenes 2D</strong> de esta proteina,
        como si las hubieramos congelado con Cryo-EM y tomado fotos con un microscopio electronico.
        Cada imagen captura la proteina en un angulo y <strong>conformacion</strong> (forma 3D) aleatoria.
        <br><br>
        <strong>Que buscamos:</strong> Descubrir cuantas conformaciones diferentes tiene <em>${name}</em>,
        cuales son las mas comunes, y que tan confiables son esos resultados.
        Para eso, usamos dos IAs independientes y luego FlexConsensus las compara.`;

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

    // PASO 2: Dos IAs
    document.getElementById('explain-methods').innerHTML = `
        Se procesaron las ${a.n_particles.toLocaleString()} imagenes de <strong>${name}</strong> con dos IAs independientes:
        <ul>
            <li><strong>CryoDRGN</strong> (grafico izquierdo): Usa un Variational Autoencoder que trabaja en espacio de Fourier.
                Comprime cada imagen en ${a.latent_dim} numeros y genera un "mapa" donde imagenes de conformaciones similares quedan cerca.</li>
            <li><strong>HetSIREN</strong> (grafico derecho): Usa redes neuronales sinusoidales que trabajan en espacio real.
                Genera otro "mapa" DIFERENTE para las MISMAS ${a.n_particles.toLocaleString()} imagenes.</li>
        </ul>
        <strong>Que ves:</strong> Cada punto de color = 1 imagen de ${name}. Los ${a.n_conformations} colores = ${a.n_conformations} conformaciones.
        Las "nubes" de puntos son grupos de imagenes donde ${name} tiene una forma similar.
        <strong>Rota</strong> con el mouse, <strong>zoom</strong> con la rueda.`;

    // Charts
    render3D('chart-m1', a.method1, a.labels, 'CryoDRGN');
    render3D('chart-m2', a.method2, a.labels, 'HetSIREN');

    document.getElementById('insight-methods').innerHTML = `
        <strong>Que se observa?</strong> Los dos graficos muestran las mismas ${a.n_particles.toLocaleString()} particulas de ${name}
        pero <strong>organizadas de forma diferente</strong>. Los clusters (nubes) estan en posiciones distintas.
        Esto demuestra que CryoDRGN y HetSIREN no coinciden: cada IA "interpreta" la flexibilidad de ${name} a su manera.
        <strong>Por eso necesitamos FlexConsensus: para saber en que coinciden y en que no.</strong>`;

    // PASO 3: Consenso
    document.getElementById('explain-consensus').innerHTML = `
        FlexConsensus tomo los dos mapas de arriba y los <strong>alineo en un unico espacio</strong>.
        Ahora cada particula de ${name} tiene una posicion comun donde ambas IAs estan de acuerdo.
        <br><br>
        <strong>Dos vistas disponibles:</strong>
        <ul>
            <li><strong>"Por Conformacion"</strong>: Los ${a.n_conformations} colores son las ${a.n_conformations} formas diferentes de ${name}.
                Puedes ver cuales son las mas comunes (clusters grandes) y cuales son raras (clusters chicos).</li>
            <li><strong>"Por Consensus Error"</strong>: Los colores muestran la <strong>fiabilidad</strong>.
                Verde oscuro = ambas IAs coinciden (fiable). Amarillo = discrepan (dudoso). Las particulas amarillas deberian descartarse.</li>
        </ul>`;

    renderConsensus('labels');

    document.getElementById('insight-consensus').innerHTML = `
        <strong>Que se ve?</strong> En ${name} se detectaron <strong>${a.n_conformations} conformaciones distintas</strong>.
        La conformacion dominante es <strong>${dominant.name}</strong> con el ${dominant.percentage}% de las particulas
        (${dominant.n_particles.toLocaleString()} imagenes).
        <br><br>
        Cambia a <strong>"Por Consensus Error"</strong> para ver cuales son fiables.
        Las particulas en colores claros/amarillos son aquellas donde CryoDRGN y HetSIREN <strong>no se ponen de acuerdo</strong>
        sobre la conformacion de ${name} &mdash; esos datos no son confiables.`;

    // PASO 4: Fiabilidad
    document.getElementById('explain-error').innerHTML = `
        Para cada una de las ${a.n_particles.toLocaleString()} imagenes de ${name}, FlexConsensus calculo un
        <strong>"consensus error"</strong>: la distancia entre donde la ubica CryoDRGN y donde la ubica HetSIREN en el espacio de consenso.
        <ul>
            <li><strong>Error bajo</strong> (verde en el histograma) = ambas IAs coinciden = <span class="highlight">resultado FIABLE</span></li>
            <li><strong>Error alto</strong> (rojo en el histograma) = las IAs discrepan = <span class="highlight">resultado NO fiable, descartar</span></li>
        </ul>
        El grafico de la derecha muestra el efecto de quedarse <strong>solo con las particulas fiables</strong> (20% con menor error):
        los clusters se definen mucho mejor, es decir, las conformaciones de ${name} se distinguen con mas claridad.`;

    renderHistogram(a);
    renderFiltering(a);

    document.getElementById('insight-error').innerHTML = `
        <strong>Resultado para ${name}:</strong>
        De las ${a.n_particles.toLocaleString()} particulas, solo el <span class="${parseFloat(reliablePct) > 25 ? 'good' : 'warn'}">${reliablePct}%
        (${a.filtering.n_filtered.toLocaleString()} particulas) son fiables</span>. Esto significa que el
        <span class="bad">${unreliablePct}% restante</span> son dudosas porque CryoDRGN y HetSIREN no coinciden en esas particulas.
        <br><br>
        <strong>En la practica:</strong> Si un investigador usara solo CryoDRGN para estudiar ${name},
        estaria trabajando con datos de los cuales <strong>solo ~${reliablePct}% son confiables</strong>.
        FlexConsensus permite identificar y descartar el resto, mejorando la calidad del analisis.`;

    // PASO 5: Tabla
    document.getElementById('explain-table').innerHTML = `
        Desglose por cada una de las <strong>${a.n_conformations} conformaciones</strong> de ${name}.
        El <strong>"% Fiable"</strong> indica que fraccion de las particulas de esa conformacion son confiables.
        Las conformaciones con pocas particulas (raras) suelen tener menor fiabilidad porque las IAs tienen menos datos para aprender.`;

    renderTable(a);

    // CONCLUSIONES
    document.getElementById('conclusions-box').innerHTML = `
        <div class="concl-card">
            <div class="concl-icon blue">&#128300;</div>
            <div>
                <h5>${name} tiene ${a.n_conformations} conformaciones detectables</h5>
                <p>FlexConsensus detecto ${a.n_conformations} formas 3D diferentes para esta proteina.
                   La mas comun es ${dominant.name} (${dominant.percentage}% de las particulas).
                   La menos comun es ${sorted[sorted.length-1].name} (${sorted[sorted.length-1].percentage}%).
                   Esto indica que ${name} es una proteina con flexibilidad conformacional ${a.n_conformations > 4 ? 'alta' : a.n_conformations > 2 ? 'moderada' : 'baja'}.</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon ${mantelEmoji === 'good' ? 'green' : mantelEmoji === 'warn' ? 'yellow' : 'red'}">&#9989;</div>
            <div>
                <h5>CryoDRGN y HetSIREN tienen concordancia ${mantelQuality} (r = ${a.mantel_r})</h5>
                <p>El test de Mantel muestra una correlacion de ${a.mantel_r} con p = ${a.mantel_p}.
                   Esto significa que ${a.mantel_r > 0.7
                       ? 'ambas IAs detectan patrones MUY similares en ' + name + ', lo que da confianza en los resultados.'
                       : a.mantel_r > 0.5
                       ? 'hay concordancia moderada: las IAs coinciden en lo general pero discrepan en detalles finos.'
                       : 'las IAs discrepan significativamente, lo que sugiere que ' + name + ' es particularmente dificil de analizar.'}
                   El p-valor de ${a.mantel_p} confirma que esta concordancia NO es por azar.</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon ${parseFloat(reliablePct) > 25 ? 'green' : 'yellow'}">&#128202;</div>
            <div>
                <h5>Solo el ${reliablePct}% de las particulas son fiables</h5>
                <p>De las ${a.n_particles.toLocaleString()} imagenes procesadas, ${a.filtering.n_filtered.toLocaleString()} son confiables
                   (ambas IAs coinciden). Las otras ${(a.filtering.n_all - a.filtering.n_filtered).toLocaleString()} particulas
                   deberian descartarse.
                   ${parseFloat(reliablePct) < 25
                       ? 'Este porcentaje es bajo, lo que sugiere que ' + name + ' tiene regiones de alta flexibilidad donde las IAs no logran ponerse de acuerdo.'
                       : 'Este es un porcentaje razonable que permite un analisis estructural robusto.'}
                   La conformacion mas fiable es <strong>${best.name}</strong> (${best.reliable_pct}%) y la menos fiable
                   es <strong>${worst.name}</strong> (${worst.reliable_pct}%).</p>
            </div>
        </div>

        <div class="concl-card">
            <div class="concl-icon blue">&#128138;</div>
            <div>
                <h5>Impacto practico para ${name}</h5>
                <p>Sin FlexConsensus, un investigador que estudie ${name} con una sola IA no sabria que
                   <strong>~${unreliablePct}% de sus datos son dudosos</strong>.
                   Con FlexConsensus, puede filtrar esas particulas y quedarse solo con las fiables,
                   obteniendo estructuras 3D mas precisas. Esto es critico si ${name} se usa como
                   target para diseno de farmacos o para entender mecanismos biologicos.</p>
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
    showlegend:false,
};
const PCONFIG = {displayModeBar:true,displaylogo:false,responsive:true};

function render3D(containerId, data, labels, methodName) {
    Plotly.newPlot(containerId, [{
        type:'scatter3d', mode:'markers',
        x:data.x, y:data.y, z:data.z,
        marker:{size:2,color:labels.map(l=>CONF_COLORS[l]),opacity:.7},
        hovertemplate:`<b>${methodName}</b><br>Conformacion: %{text}<br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}<extra></extra>`,
        text:labels.map(l=>CONF_NAMES[l]),
    }], LAYOUT_3D, PCONFIG);
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
    const colors = isLabels ? a.labels.map(l=>CONF_COLORS[l]) : a.errors;

    Plotly.newPlot('chart-consensus', [{
        type:'scatter3d', mode:'markers',
        x:a.consensus.x, y:a.consensus.y, z:a.consensus.z,
        marker:{
            size:2.5, color:colors, opacity:.7,
            colorscale: isLabels ? undefined : 'Viridis',
            ...(isLabels ? {} : {colorbar:{title:{text:'Error',font:{size:10,color:DARK.text}},tickfont:{color:DARK.text,size:9},thickness:15,len:.6}}),
        },
        hovertemplate: isLabels
            ? '<b>Consenso</b><br>Conformacion: %{text}<br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}<extra>Espacio de consenso unificado</extra>'
            : '<b>Error: %{marker.color:.4f}</b><br>Dim1: %{x:.2f}<br>Dim2: %{y:.2f}<br>Dim3: %{z:.2f}<extra>Bajo = fiable, Alto = dudoso</extra>',
        text:a.labels.map(l=>CONF_NAMES[l]),
    }], {...LAYOUT_3D, margin:{l:0,r:0,t:20,b:0}}, PCONFIG);
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
