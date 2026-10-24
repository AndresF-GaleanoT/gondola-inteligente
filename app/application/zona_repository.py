# APPLICATION / zona_repository - puerto de persistencia de zonas.
# Los casos de uso y la interfaz HTTP dependen de este contrato, no de COMO ni
# DONDE se guardan las zonas (JSON en disco hoy; una base de datos manana sin
# tocar a quien lo consume). El adaptador concreto vive en
# app/infrastructure/zona_repository_json.py.

from typing import List, Protocol


class ZonaRepository(Protocol):
    """Puerto (Protocol) para la persistencia de las zonas de calibracion."""

    def obtener(self) -> List[dict]:
        """Zonas vigentes: las personalizadas si existen y son validas, si no
        las de fabrica."""
        ...

    def guardar(self, zonas: List[dict]) -> List[dict]:
        """Valida y persiste las zonas editadas. Devuelve la lista validada;
        lanza ValueError si alguna zona es invalida."""
        ...

    def restablecer(self) -> List[dict]:
        """Descarta la personalizacion y vuelve a las zonas de fabrica."""
        ...

    def fuente(self) -> str:
        """'runtime' si hay zonas personalizadas vigentes, 'default' si no."""
        ...
