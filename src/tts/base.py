"""
Clase base abstracta para servicios TTS.
"""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseTTSClient(ABC):
    """Clase base abstracta para clientes TTS."""
    
    def __init__(
        self,
        model: str,
        voice: str,
        speed: float = 1.0,
        output_format: str = "mp3",
    ):
        self.model = model
        self.voice = voice
        self.speed = speed
        self.output_format = output_format
    
    @abstractmethod
    async def generate_audio(
        self,
        text: str,
        output_path: Path,
    ) -> Path:
        """
        Genera audio a partir de texto.
        
        Args:
            text: El texto a convertir en audio
            output_path: Ruta donde guardar el audio
        
        Returns:
            Path al archivo de audio generado
        """
        pass
    
    @abstractmethod
    async def get_available_voices(self) -> list[str]:
        """
        Obtiene las voces disponibles.
        
        Returns:
            Lista de nombres de voces disponibles
        """
        pass
