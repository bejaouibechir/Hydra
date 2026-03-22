"""
JSON Connector - Sprint 4
Projet Hydra ETL

Connecteur unique pour JSON/JSONL avec support nested intelligent.

Fonctionnalités Sprint 4:
- Extract depuis fichier local (JSON, JSONL)
- Support JSON flat
- Support JSON nested simple (1-3 niveaux)
- Auto-flatten avec pandas json_normalize
- Batch processing
- Gestion erreurs robuste

Formats supportés:
- JSON standard: {"key": "value"} ou [{"id": 1}, ...]
- JSONL (JSON Lines): {"id": 1}\n{"id": 2}\n

Limitations Sprint 4:
- URL extraction → Sprint 5+
- Load operation → Sprint 5+
- JSONPath filtering → Sprint 5+
- Schema mapping explicite → Sprint 5+

POC Validation:
- 7/7 tests passent
- Performance: 10k records en ~3s
- Approche: pandas json_normalize validée

Architecture:
    JSONConnector (hérite BaseConnector)
    ├── extract_batches()           ← Entry point
    ├── _extract_from_file()        ← Dispatch format
    ├── _extract_json()             ← JSON standard
    ├── _extract_jsonl()            ← JSON Lines
    └── _flatten_records()          ← Pandas normalize

Examples:
    >>> # JSON flat
    >>> conn = JSONConnector(name="my_json", config={
    ...     "type": "json",
    ...     "extract": {}
    ... })
    >>> for batch in conn.extract_batches(file="data.json"):
    ...     print(batch)
    
    >>> # JSON nested avec flatten
    >>> for batch in conn.extract_batches(file="nested.json", flatten_depth=2):
    ...     print(batch)
    
    >>> # JSONL avec batch_size custom
    >>> for batch in conn.extract_batches(file="events.jsonl", batch_size=5000):
    ...     print(batch)

Author: Hydra Consortium (ChatGPT, Grok, Claude)
Date: Janvier 2026
Sprint: 4
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional
import warnings

import pandas as pd
from pandas import json_normalize

from internal.connector.interface import Connector, Batch


class JSONConnector(Connector):
    """
    Connecteur JSON/JSONL avec support nested intelligent.
    
    Utilise pandas json_normalize pour flatten automatique avec contrôle
    granulaire de la profondeur (0-3 niveaux).
    
    Capabilities Sprint 4:
    - supports_extract: True
    - supports_load: False (Sprint 5+)
    - supports_upsert: False
    - supports_incremental: False
    
    Formats:
    - .json: JSON standard (objet ou array)
    - .jsonl, .ndjson: JSON Lines (streaming)
    
    Configuration:
        sources:
          my_json:
            type: json
            extract:
              file: "data/users.json"      # Requis Sprint 4
              batch_size: 10000             # Optionnel (défaut: 10000)
              flatten_depth: 1              # Optionnel (0-3, défaut: 1)
    
    Args:
        name: Nom du connecteur
        config: Configuration (type, extract, etc.)
    
    Attributes:
        _extract_cfg: Configuration extract depuis config
    
    Raises:
        ValueError: Configuration invalide
        FileNotFoundError: Fichier introuvable
        JSONDecodeError: JSON invalide
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialise le connecteur JSON.
        
        Args:
            name: Nom du connecteur (pour logs)
            config: Dict avec 'type', 'extract', etc.
        """
        super().__init__(name=name, config=config)
        self._extract_cfg = config.get("extract", {})
    
    # ========================================================================
    # Capabilities
    # ========================================================================
    
    def supports_extract(self) -> bool:
        """
        Support extraction.
        
        Returns:
            True (toujours pour Sprint 4)
        """
        return True
    
    def supports_load(self) -> bool:
        """
        Support load (write).
        
        Returns:
            False (Sprint 5+)
        """
        return False
    
    def get_capabilities(self) -> Dict[str, Any]:
        """
        Retourne capabilities du connecteur.
        
        Returns:
            Dict avec features supportées
        """
        return {
            "supports_extract": True,
            "supports_load": False,
            "supports_upsert": False,
            "supports_incremental": False,
            "formats": ["json", "jsonl", "ndjson"],
            "flatten_max_depth": 3,
            "streaming": True,
        }
    
    def test_connection(self) -> None:
        """
        Test connection pour JSON connector.
        
        Pour JSON (fichier local), on vérifie juste que le fichier
        existe et est lisible (si spécifié dans config).
        
        Raises:
            ValueError: Si fichier spécifié mais introuvable/illisible
        """
        # Pour JSON, pas vraiment de "connexion" à tester
        # On pourrait vérifier le fichier s'il est dans config
        file_path = self._extract_cfg.get("file")
        
        if file_path:
            path = Path(file_path)
            if not path.exists():
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"Fichier de test introuvable: {file_path}"
                )
            if not path.is_file():
                raise ValueError(
                    f"{self.__class__.__name__} [{self.name}]: "
                    f"Chemin n'est pas un fichier: {file_path}"
                )
        # Pas de fichier dans config → connexion OK (sera fourni à extract_batches)
    
    def load_batches(
        self,
        batches,
        *,
        table: str,
        mode: str = "append",
        key: Optional[List[str]] = None,
    ) -> None:
        """
        Load batches (non implémenté Sprint 4).
        
        Sprint 5+ : Écriture JSON/JSONL.
        
        Raises:
            NotImplementedError: Sprint 5+
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} [{self.name}]: "
            f"Load operation disponible Sprint 5+. "
            f"Sprint 4 supporte extract uniquement."
        )
    
    # ========================================================================
    # Extract - Entry Point
    # ========================================================================
    
    def extract_batches(
        self,
        *,
        file: Optional[str] = None,
        url: Optional[str] = None,
        batch_size: int = 10_000,
        flatten_depth: int = 1,
        json_path: Optional[str] = None,
    ) -> Iterator[Batch]:
        """
        Extrait batches depuis JSON/JSONL.
        
        Entry point principal pour extraction. Détecte automatiquement
        le format (JSON vs JSONL) basé sur l'extension du fichier.
        
        Args:
            file: Chemin fichier local (requis Sprint 4)
                Exemples:
                - "data/users.json"
                - "logs/events.jsonl"
                - "C:/data/nested.json"
            
            url: URL distante (Sprint 5+, non implémenté)
                Exemples (futurs):
                - "https://api.example.com/users"
                - "http://localhost:8000/data.json"
            
            batch_size: Taille des batches (défaut: 10000)
                Nombre de records par batch. Plus grand = moins d'I/O
                mais plus de mémoire.
            
            flatten_depth: Profondeur auto-flatten (0-3, défaut: 1)
                - 0: Pas de flatten (garde nested)
                - 1: Flatten 1 niveau (user.name)
                - 2: Flatten 2 niveaux (user.address.city)
                - 3: Flatten 3 niveaux (max)
            
            json_path: JSONPath extraction (Sprint 5+, non implémenté)
                Exemples (futurs):
                - "$.data[*]"
                - "$.users[?(@.active)]"
        
        Yields:
            Batch: Liste de dict (records JSON flatten)
        
        Raises:
            ValueError: Paramètres invalides ou mutuellement exclusifs
            NotImplementedError: Feature Sprint 5+ demandée
            FileNotFoundError: Fichier introuvable
            JSONDecodeError: JSON invalide
        
        Examples:
            >>> # Extraction simple
            >>> conn = JSONConnector(name="test", config={"type": "json"})
            >>> for batch in conn.extract_batches(file="data.json"):
            ...     process(batch)
            
            >>> # Avec flatten custom
            >>> for batch in conn.extract_batches(
            ...     file="nested.json",
            ...     flatten_depth=2,
            ...     batch_size=5000
            ... ):
            ...     process(batch)
            
            >>> # JSONL streaming
            >>> for batch in conn.extract_batches(file="events.jsonl"):
            ...     process(batch)
        """
        # Validation paramètres
        if not file and not url:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Paramètre 'file' ou 'url' requis pour extract."
            )
        
        if file and url:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Paramètres 'file' et 'url' mutuellement exclusifs. "
                f"Utilisez l'un ou l'autre, pas les deux."
            )
        
        if url:
            raise NotImplementedError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Extraction URL disponible Sprint 5+. "
                f"Utilisez 'file' pour Sprint 4."
            )
        
        if json_path:
            raise NotImplementedError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"JSONPath filtering disponible Sprint 5+."
            )
        
        if not isinstance(flatten_depth, int) or not 0 <= flatten_depth <= 3:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'flatten_depth' doit être entre 0 et 3, reçu: {flatten_depth}"
            )
        
        if not isinstance(batch_size, int) or batch_size < 1:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"'batch_size' doit être >= 1, reçu: {batch_size}"
            )
        
        # Extraction depuis fichier
        yield from self._extract_from_file(
            file=file,
            batch_size=batch_size,
            flatten_depth=flatten_depth,
        )
    
    # ========================================================================
    # Extract - Helpers
    # ========================================================================
    
    def _extract_from_file(
        self,
        *,
        file: str,
        batch_size: int,
        flatten_depth: int,
    ) -> Iterator[Batch]:
        """
        Extraction depuis fichier local.
        
        Détecte automatiquement le format basé sur l'extension:
        - .json → JSON standard (objet ou array)
        - .jsonl, .ndjson → JSON Lines (streaming)
        - Autres → Tentative JSON standard avec warning
        
        Args:
            file: Chemin fichier
            batch_size: Taille batches
            flatten_depth: Profondeur flatten
        
        Yields:
            Batch
        
        Raises:
            FileNotFoundError: Fichier introuvable
            ValueError: Fichier n'est pas un fichier régulier
        """
        file_path = Path(file)
        
        # Validation existence
        if not file_path.exists():
            raise FileNotFoundError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Fichier introuvable: {file}\n"
                f"  Chemin absolu: {file_path.absolute()}"
            )
        
        if not file_path.is_file():
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Chemin n'est pas un fichier régulier: {file}"
            )
        
        # Détection format par extension
        suffix = file_path.suffix.lower()
        
        if suffix in [".jsonl", ".ndjson"]:
            # JSON Lines (streaming)
            yield from self._extract_jsonl(file_path, batch_size, flatten_depth)
        
        elif suffix in [".json"]:
            # JSON standard
            yield from self._extract_json(file_path, batch_size, flatten_depth)
        
        else:
            # Extension inconnue → tentative JSON standard avec warning
            warnings.warn(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Extension inconnue '{suffix}' pour fichier '{file_path.name}'. "
                f"Tentative de lecture comme JSON standard.",
                RuntimeWarning
            )
            yield from self._extract_json(file_path, batch_size, flatten_depth)
    
    def _extract_json(
        self,
        file_path: Path,
        batch_size: int,
        flatten_depth: int,
    ) -> Iterator[Batch]:
        """
        Extraction JSON standard.
        
        Supporte:
        - Objet unique: {"key": "value"}
        - Array d'objets: [{"id": 1}, {"id": 2}]
        
        Args:
            file_path: Path objet
            batch_size: Taille batches
            flatten_depth: Profondeur flatten
        
        Yields:
            Batch
        
        Raises:
            ValueError: JSON invalide ou format non supporté
        """
        # Lecture fichier complet
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        except json.JSONDecodeError as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"JSON invalide dans '{file_path.name}'.\n"
                f"  Ligne {e.lineno}, colonne {e.colno}: {e.msg}\n"
                f"  Vérifiez la syntaxe JSON avec un validateur en ligne."
            ) from e
        
        except UnicodeDecodeError as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Encodage invalide dans '{file_path.name}'. "
                f"Le fichier doit être en UTF-8.\n"
                f"  Erreur: {e}"
            ) from e
        
        except Exception as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Erreur lecture '{file_path.name}': {e}"
            ) from e
        
        # Normaliser en liste de records
        if isinstance(data, dict):
            # Objet unique → liste de 1 élément
            records = [data]
        
        elif isinstance(data, list):
            # Array → déjà liste
            if not data:
                # Liste vide → return sans yield
                return
            records = data
        
        else:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Format JSON non supporté dans '{file_path.name}'. "
                f"Attendu: dict ou list, reçu: {type(data).__name__}\n"
                f"  Le fichier doit contenir un objet {{}} ou un array []."
            )
        
        # Flatten si demandé
        if flatten_depth > 0:
            records = self._flatten_records(records, flatten_depth)
        
        # Yield par batches
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            yield batch
    
    def _extract_jsonl(
        self,
        file_path: Path,
        batch_size: int,
        flatten_depth: int,
    ) -> Iterator[Batch]:
        """
        Extraction JSONL (JSON Lines).
        
        Format: 1 objet JSON par ligne.
        Optimisé pour streaming (pas de chargement complet en mémoire).
        
        Args:
            file_path: Path objet
            batch_size: Taille batches
            flatten_depth: Profondeur flatten
        
        Yields:
            Batch
        
        Raises:
            ValueError: JSON invalide sur une ligne
        """
        batch = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    line = line.strip()
                    
                    # Ignorer lignes vides
                    if not line:
                        continue
                    
                    # Parse JSON
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as e:
                        raise ValueError(
                            f"{self.__class__.__name__} [{self.name}]: "
                            f"JSON invalide dans '{file_path.name}' ligne {line_num}.\n"
                            f"  Erreur: {e.msg}\n"
                            f"  Ligne: {line[:100]}..."
                        ) from e
                    
                    batch.append(record)
                    
                    # Yield batch si plein
                    if len(batch) >= batch_size:
                        if flatten_depth > 0:
                            batch = self._flatten_records(batch, flatten_depth)
                        yield batch
                        batch = []
                
                # Yield dernier batch (peut être partiel)
                if batch:
                    if flatten_depth > 0:
                        batch = self._flatten_records(batch, flatten_depth)
                    yield batch
        
        except UnicodeDecodeError as e:
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Encodage invalide dans '{file_path.name}'. "
                f"Le fichier doit être en UTF-8.\n"
                f"  Erreur: {e}"
            ) from e
        
        except Exception as e:
            # Re-raise si déjà ValueError
            if isinstance(e, ValueError):
                raise
            
            raise ValueError(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Erreur lecture '{file_path.name}': {e}"
            ) from e
    
    def _flatten_records(
        self,
        records: List[Dict[str, Any]],
        flatten_depth: int,
    ) -> List[Dict[str, Any]]:
        """
        Flatten nested JSON avec pandas json_normalize.
        
        Utilise pandas.json_normalize qui gère:
        - Nested objects (user.name → user.name)
        - Max depth control
        - Missing keys → NaN (converti en None)
        
        Si flatten échoue, retourne records originaux avec warning
        (graceful degradation).
        
        Args:
            records: Liste de dict (JSON objects)
            flatten_depth: Profondeur (1-3)
        
        Returns:
            Liste de dict flatten (ou originaux si échec)
        
        Notes:
            - NaN pandas converti en None pour compatibilité JSON
            - Flatten failure → warning + return original
        
        Examples:
            >>> records = [{"id": 1, "user": {"name": "Alice"}}]
            >>> flatten_records(records, 1)
            [{"id": 1, "user.name": "Alice"}]
        """
        if not records:
            return records
        
        try:
            # Pandas json_normalize (POC validé)
            df = json_normalize(records, max_level=flatten_depth)
            
            # Convertir NaN → None (pour JSON serialization)
            df = df.where(pd.notna(df), None)
            
            # Convertir back to list of dict
            return df.to_dict('records')
        
        except Exception as e:
            # Flatten échoué → warning + return original (graceful degradation)
            warnings.warn(
                f"{self.__class__.__name__} [{self.name}]: "
                f"Flatten échoué (depth={flatten_depth}). "
                f"Données retournées non-flatten.\n"
                f"  Erreur: {type(e).__name__}: {e}\n"
                f"  Conseil: Vérifiez la structure des données ou réduisez flatten_depth.",
                RuntimeWarning
            )
            return records