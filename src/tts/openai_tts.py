"""
Cliente TTS de OpenAI.
"""

import logging
from pathlib import Path
from typing import Optional
import uuid

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import get_config
from .base import BaseTTSClient

logger = logging.getLogger(__name__)


class OpenAITTS(BaseTTSClient):
    """Cliente TTS de OpenAI."""
    
    # Voces disponibles en OpenAI TTS
    AVAILABLE_VOICES = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def __init__(
        self,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        output_format: Optional[str] = None,
    ):
        config = get_config()
        
        super().__init__(
            model=model or config.tts.model,
            voice=voice or config.tts.voice,
            speed=speed or config.tts.speed,
            output_format=output_format or config.tts.output_format,
        )
        
        self.config = config
        self.client = AsyncOpenAI(api_key=config.openai_api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def generate_audio(
        self,
        text: str,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Genera audio a partir de texto usando OpenAI TTS.
        
        Args:
            text: El texto a convertir en audio
            output_path: Ruta donde guardar el audio (opcional)
        
        Returns:
            Path al archivo de audio generado
        """
        
        # Generar nombre de archivo si no se especifica
        if output_path is None:
            output_dir = self.config.get_audio_output_path()
            filename = f"news_{uuid.uuid4().hex[:8]}.{self.output_format}"
            output_path = output_dir / filename
        
        # Asegurar que el directorio existe
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # OpenAI TTS tiene un límite de 4096 caracteres por petición
            # Si el texto es más largo, dividirlo en chunks
            max_chars = 4000
            
            if len(text) <= max_chars:
                await self._generate_single_audio(text, output_path)
            else:
                await self._generate_chunked_audio(text, output_path, max_chars)
            
            logger.info(f"Generated audio: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error generating audio: {e}")
            raise
    
    async def _generate_single_audio(self, text: str, output_path: Path) -> None:
        """Genera un solo archivo de audio."""
        response = await self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
            speed=self.speed,
            response_format=self.output_format,
        )
        
        # Guardar el audio
        with open(output_path, "wb") as f:
            async for chunk in response.iter_bytes():
                f.write(chunk)
    
    async def _generate_chunked_audio(
        self,
        text: str,
        output_path: Path,
        max_chars: int
    ) -> None:
        """Genera audio en chunks y los combina."""
        import tempfile
        import os
        
        # Dividir el texto en chunks por oraciones
        chunks = self._split_text_by_sentences(text, max_chars)
        
        temp_files = []
        
        try:
            # Generar audio para cada chunk
            for i, chunk in enumerate(chunks):
                temp_path = output_path.parent / f"_temp_{i}_{output_path.name}"
                
                response = await self.client.audio.speech.create(
                    model=self.model,
                    voice=self.voice,
                    input=chunk,
                    speed=self.speed,
                    response_format=self.output_format,
                )
                
                with open(temp_path, "wb") as f:
                    async for audio_chunk in response.iter_bytes():
                        f.write(audio_chunk)
                
                temp_files.append(temp_path)
            
            # Combinar los archivos de audio
            await self._combine_audio_files(temp_files, output_path)
            
        finally:
            # Limpiar archivos temporales
            for temp_file in temp_files:
                if temp_file.exists():
                    temp_file.unlink()
    
    def _split_text_by_sentences(self, text: str, max_chars: int) -> list[str]:
        """Divide el texto en chunks respetando oraciones."""
        import re
        
        # Dividir por oraciones
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chars:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    async def _combine_audio_files(self, input_files: list[Path], output_path: Path) -> None:
        """Combina múltiples archivos de audio en uno solo."""
        # Para MP3, se pueden concatenar directamente
        if self.output_format == "mp3":
            with open(output_path, "wb") as outfile:
                for input_file in input_files:
                    with open(input_file, "rb") as infile:
                        outfile.write(infile.read())
        else:
            # Para otros formatos, usar el primer archivo como fallback
            # En producción, se usaría ffmpeg u otra herramienta
            import shutil
            if input_files:
                shutil.copy(input_files[0], output_path)
                for f in input_files[1:]:
                    with open(output_path, "ab") as outfile:
                        with open(f, "rb") as infile:
                            outfile.write(infile.read())
    
    async def get_available_voices(self) -> list[str]:
        """Obtiene las voces disponibles en OpenAI TTS."""
        return self.AVAILABLE_VOICES


def get_tts_client() -> BaseTTSClient:
    """Factory para obtener el cliente TTS según la configuración."""
    config = get_config()
    provider = config.tts.provider.lower()
    
    if provider == "openai":
        return OpenAITTS()
    else:
        # Por defecto, usar OpenAI
        logger.warning(f"Unknown TTS provider: {provider}, using OpenAI")
        return OpenAITTS()
