"""
Visualización 3: Comparación Antes/Después del filtrado
Muestra el efecto de filtrar partículas no fiables
"""
import numpy as np
import matplotlib.pyplot as plt

# Cargar datos
latent_space = np.load('../Espacio_Consenso/latent_space.npy')
labels = np.load('../Espacio_Consenso/particle_labels.npy')
errors = np.load('../Metricas_Error/consensus_errors.npy')

# Filtrar: 20% con menor error = más fiables
low_error = errors < np.percentile(errors, 20)

fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Antes (todas las partículas)
axes[0].scatter(
    latent_space[:, 0], latent_space[:, 1],
    c='gray', alpha=0.3, s=2
)
axes[0].set_title(f'Todas las particulas ({len(latent_space):,})', fontsize=13)
axes[0].set_xlabel('Dim 1')
axes[0].set_ylabel('Dim 2')

# Después (solo las fiables)
scatter = axes[1].scatter(
    latent_space[low_error, 0], latent_space[low_error, 1],
    c=labels[low_error], cmap='viridis', s=5, alpha=0.7
)
axes[1].set_title(
    f'Particulas fiables ({sum(low_error):,}/{len(low_error):,})', fontsize=13
)
axes[1].set_xlabel('Dim 1')
axes[1].set_ylabel('Dim 2')
plt.colorbar(scatter, ax=axes[1], label='Clase conformacional')

plt.suptitle('Efecto del filtrado por Consensus Error', fontsize=15)
plt.tight_layout()
plt.savefig('comparacion_filtro.png', dpi=300, bbox_inches='tight')
plt.show()
print("Guardado: comparacion_filtro.png")
