"""
Visualización 2: Distribución de consensus error
Genera histograma de errores con umbral de fiabilidad
"""
import numpy as np
import matplotlib.pyplot as plt

# Cargar errores
errors = np.load('../Metricas_Error/consensus_errors.npy')

plt.figure(figsize=(10, 6))
plt.hist(errors, bins=50, alpha=0.7, color='steelblue', edgecolor='white')
plt.axvline(
    x=np.percentile(errors, 80), color='red',
    linestyle='--', linewidth=2, label='Umbral 80% (datos fiables)'
)
plt.axvline(
    x=np.median(errors), color='orange',
    linestyle=':', linewidth=2, label=f'Mediana ({np.median(errors):.3f})'
)
plt.xlabel('Consensus Error', fontsize=12)
plt.ylabel('Numero de particulas', fontsize=12)
plt.title('Distribucion de Consensus Error - IgG-RL', fontsize=14)
plt.legend(fontsize=11)
plt.grid(axis='y', alpha=0.3)
plt.savefig('distribucion_errores.png', dpi=300, bbox_inches='tight')
plt.show()
print("Guardado: distribucion_errores.png")
