"""
Visualización 1: Espacio de consenso 3D
Genera scatter plot 3D del espacio latente de FlexConsensus
"""
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D

# Cargar espacio latente (coordenadas)
latent_space = np.load('../Espacio_Consenso/latent_space.npy')
labels = np.load('../Espacio_Consenso/particle_labels.npy')

# Graficar
fig = plt.figure(figsize=(10, 8))
ax = fig.add_subplot(111, projection='3d')
scatter = ax.scatter(
    latent_space[:, 0], latent_space[:, 1], latent_space[:, 2],
    c=labels, cmap='viridis', s=5, alpha=0.6
)
plt.colorbar(scatter, label='Clase conformacional')
ax.set_xlabel('Dim 1')
ax.set_ylabel('Dim 2')
ax.set_zlabel('Dim 3')
plt.title('Espacio de Consenso FlexConsensus - IgG-RL')
plt.savefig('espacio_consenso_3d.png', dpi=300, bbox_inches='tight')
plt.show()
print("Guardado: espacio_consenso_3d.png")
