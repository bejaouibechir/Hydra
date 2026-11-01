"""
MongoDB connector for Hydra.

Implements Connector interface for MongoDB with schema inference,
document normalization, and batch extraction.
"""

from typing import Dict, List, Any, Optional, Iterator
import logging

try:
    from pymongo import MongoClient
    from pymongo.database import Database
    from pymongo.collection import Collection
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

from hydra_etl.internal.connector.interface import Connector
from hydra_etl.internal.schema import SchemaDescriptor, SchemaMode
from hydra_etl.internal.schema.policies import DriftPolicy, SchemaDriftError

from .schema_detector import SchemaDetector
from .normalizer import DocumentNormalizer
from .query_builder import QueryBuilder

logger = logging.getLogger(__name__)


class MongoDBConnector(Connector):
    """
    MongoDB connector with automatic schema inference and document normalization.
    
    Features:
    - Automatic schema detection from sample documents
    - Nested document flattening
    - Array handling (keep/flatten/explode)
    - Schema drift detection and adaptation
    - Batch extraction with cursor
    
    Configuration:
        sources:
          mongodb_source:
            type: mongodb
            connection:
              uri: "mongodb://localhost:27017"
              database: mydb
              # OR separate components:
              host: localhost
              port: 27017
              username: user
              password: pass
              database: mydb
            extract:
              collection: orders
              filter: {"status": "active"}  # Optional
              limit: 1000                    # Optional
            schema:  # Optional
              mode: infer_strict
              fields:
                - name: order_id
                  path: _id
                  type: string
                  required: true
                - name: customer_name
                  path: customer.name
                  type: string
              drift_policy: warn
    
    Examples:
        connector = MongoDBConnector(
            name="mongodb_source",
            config={
                "connection": {"uri": "mongodb://localhost:27017", "database": "mydb"},
                "extract": {"collection": "orders"}
            }
        )
        
        connector.connect()
        
        for batch in connector.extract_batches():
            print(f"Got {len(batch)} records")
    """
    
    def __init__(self, name: str, config: Dict[str, Any]):
        """
        Initialize MongoDB connector.
        
        Args:
            name: Connector name
            config: Configuration dictionary
        """
        super().__init__(name, config)
        
        if not PYMONGO_AVAILABLE:
            raise ImportError(
                "pymongo is required for MongoDB connector. "
                'Install it with: pip install "hydra-etl[mongodb]"'
            )
        
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.collection: Optional[Collection] = None
        
        self.schema: Optional[SchemaDescriptor] = None
        self.schema_detector = SchemaDetector()
        self.normalizer: Optional[DocumentNormalizer] = None
        self.query_builder = QueryBuilder()
        
        # Parse configuration
        self._parse_config()
    
    def _parse_config(self) -> None:
        """Parse and validate configuration."""
        conn_config = self.config.get("connection", {})
        
        # Get connection details
        if "uri" in conn_config:
            self.uri = conn_config["uri"]
        else:
            # Build URI from components
            host = conn_config.get("host", "localhost")
            port = conn_config.get("port", 27017)
            username = conn_config.get("username")
            password = conn_config.get("password")
            
            if username and password:
                self.uri = f"mongodb://{username}:{password}@{host}:{port}/"
            else:
                self.uri = f"mongodb://{host}:{port}/"
        
        self.database_name = conn_config.get("database")
        if not self.database_name:
            raise ValueError("MongoDB database name is required")
        
        # Extract configuration (fallback vers load.collection pour usage destination)
        extract_config = self.config.get("extract", {})
        load_config = self.config.get("load", {})
        self.collection_name = (
            extract_config.get("collection")
            or load_config.get("collection")
            or load_config.get("table")  # alias résolu par DestinationParser
        )
        if not self.collection_name:
            raise ValueError("MongoDB collection name is required")
        
        self.filter = extract_config.get("filter", {})
        self.limit = extract_config.get("limit")
        self.batch_size = extract_config.get("batch_size", 1000)
        
        # Schema configuration
        schema_config = self.config.get("schema", {})
        self.schema_mode = SchemaMode(schema_config.get("mode", "auto"))
        self.drift_policy = DriftPolicy(schema_config.get("drift_policy", "warn"))
        self.sample_size = int(schema_config.get("sample_size") or 100)
        # Dérive : nombre de documents portant chaque champ inconnu du schéma.
        self._drift_seen: Dict[str, int] = {}
        
        # Manual schema fields (if provided)
        self.manual_schema_fields = schema_config.get("fields", [])
    
    def connect(self) -> None:
        """Establish connection to MongoDB."""
        try:
            logger.info(f"Connecting to MongoDB: {self.database_name}.{self.collection_name}")
            
            self.client = MongoClient(self.uri)
            self.db = self.client[self.database_name]
            self.collection = self.db[self.collection_name]
            
            # Test connection
            self.client.admin.command('ping')
            
            logger.info("MongoDB connection established")
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.db = None
            self.collection = None
            logger.info("MongoDB connection closed")
    
    def test_connection(self) -> bool:
        """
        Test MongoDB connection.
        
        Returns:
            True if connection successful
        """
        try:
            if not self.client:
                self.connect()
            
            self.client.admin.command('ping')
            
            # Check if collection exists
            collection_names = self.db.list_collection_names()
            if self.collection_name not in collection_names:
                logger.warning(f"Collection '{self.collection_name}' not found")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def _ensure_schema(self) -> None:
        """Ensure schema is initialized (auto-detect if needed)."""
        if self.schema is not None:
            return
        
        if self.schema_mode == SchemaMode.MANUAL and self.manual_schema_fields:
            # Use manual schema
            self.schema = SchemaDescriptor.from_dict({
                "mode": "manual",
                "fields": self.manual_schema_fields,
                "drift_policy": self.drift_policy.value
            })
            logger.info(f"Using manual schema with {len(self.schema.fields)} fields")
        
        else:
            # Auto-detect schema
            logger.info("Auto-detecting schema from sample documents...")
            
            sample_docs = list(self.collection.find(self.filter).limit(self.sample_size))
            
            if not sample_docs:
                raise ValueError(f"No documents found in {self.collection_name}")
            
            self.schema = self.schema_detector.infer_schema(
                sample_docs,
                mode=self.schema_mode
            )
            
            logger.info(
                f"Auto-detected schema with {len(self.schema.fields)} fields "
                f"from {len(sample_docs)} sample documents"
            )
        
        # Initialize normalizer
        self.normalizer = DocumentNormalizer(self.schema)
    
    def extract_batches(self, **kwargs) -> Iterator[List[Dict[str, Any]]]:
        """
        Extract data in batches from MongoDB.
        
        Yields:
            Batches of normalized flat dictionaries
        """
        if not self.client:
            self.connect()
        
        # Ensure schema is ready
        self._ensure_schema()
        
        try:
            # Build query
            query = self.query_builder.build(
                collection=self.collection_name,
                filter=self.filter,
                limit=self.limit
            )
            
            # Execute query with cursor
            cursor = self.collection.find(query["filter"])
            
            if self.limit:
                cursor = cursor.limit(self.limit)
            
            # Process in batches
            batch = []
            total_processed = 0
            
            self._drift_seen = {}
            position = 0
            for doc in cursor:
                position += 1
                # Dérive : AVANT la normalisation, qui ne garde que les champs
                # du schéma (un champ nouveau y disparaîtrait sans trace).
                self._handle_drift(doc, position)
                normalized = self.normalizer.normalize_document(doc)
                batch.append(normalized)
                
                # Yield batch when full
                if len(batch) >= self.batch_size:
                    total_processed += len(batch)
                    logger.debug(f"Yielding batch of {len(batch)} records (total: {total_processed})")
                    yield batch
                    batch = []
            
            # Yield remaining records
            if batch:
                total_processed += len(batch)
                logger.debug(f"Yielding final batch of {len(batch)} records (total: {total_processed})")
                yield batch
            
            if self._drift_seen and self.drift_policy == DriftPolicy.WARN:
                summary = ", ".join(f"'{k}' ({n} doc.)" for k, n in sorted(self._drift_seen.items()))
                logger.warning(
                    f"MongoDB source '{self.name}': schema drift in '{self.collection_name}': "
                    f"fields not in the schema were dropped: {summary}. "
                    f"Use drift_policy: adapt to keep them, or declare them in schema.fields."
                )
            logger.info(f"Extraction complete: {total_processed} records processed")
            
        except Exception as e:
            logger.error(f"Error during extraction: {e}")
            raise
    
    # ------------------------------------------------------------------
    # Dérive de schéma
    # ------------------------------------------------------------------

    def _new_fields(self, doc: Dict[str, Any]) -> List[str]:
        """Chemins du document absents du schéma (notation pointée, comme
        l'inférence). Un chemin couvert par un champ parent du schéma
        (`customer` de type object pour `customer.name`) n'est pas nouveau."""
        known = [(f.path or f.name) for f in self.schema.fields]
        known_set = set(known)
        out: List[str] = []
        for path in self.schema_detector._flatten_document(doc):
            if path in known_set:
                continue
            if any(path.startswith(k + ".") or path.startswith(k + "[") for k in known):
                continue
            out.append(path)
        return out

    def _handle_drift(self, doc: Dict[str, Any], position: int) -> None:
        """Applique drift_policy aux champs inconnus du schéma.

        - fail   : arrêt, avec le champ et la position du document ;
        - warn   : champ écarté, avertissement (une fois par champ + bilan) ;
        - ignore : champ écarté, sans message ;
        - adapt  : champ ajouté au schéma et conservé dans la sortie.

        En mode `manual`, le schéma déclaré est le contrat : les autres
        champs sont écartés par conception, ce n'est pas une dérive.
        """
        if self.schema_mode == SchemaMode.MANUAL:
            return
        new = self._new_fields(doc)
        if not new:
            return
        if self.drift_policy == DriftPolicy.FAIL:
            raise SchemaDriftError(
                f"MongoDB source '{self.name}': schema drift in '{self.collection_name}', "
                f"document #{position}: field(s) {', '.join(repr(n) for n in new)} not in the "
                f"schema (drift_policy: fail). Declare them in schema.fields, or use "
                f"drift_policy: adapt or warn."
            )
        if self.drift_policy == DriftPolicy.ADAPT:
            stats = self.schema_detector._analyze_fields([doc])
            for path in new:
                desc = self.schema_detector._create_field_descriptor(
                    field_name=path, stats=stats[path], total_docs=1,
                    required_threshold=1.01,   # apparu en cours de route : jamais requis
                )
                if self.schema.get_field(desc.name) is None:
                    self.schema.add_field(desc)
                logger.info(
                    f"MongoDB source '{self.name}': schema extended with field '{desc.name}' "
                    f"({desc.type.value}) at document #{position} (drift_policy: adapt)"
                )
            self.normalizer = DocumentNormalizer(self.schema)
            return
        for path in new:
            first = path not in self._drift_seen
            self._drift_seen[path] = self._drift_seen.get(path, 0) + 1
            if first and self.drift_policy == DriftPolicy.WARN:
                logger.warning(
                    f"MongoDB source '{self.name}': schema drift in '{self.collection_name}', "
                    f"document #{position}: new field '{path}' is not in the schema and is "
                    f"dropped (drift_policy: warn)"
                )

    def load_batches(self, batches: Iterator[List[Dict[str, Any]]], **kwargs) -> None:
        """
        Load data batches into MongoDB.
        
        Args:
            batches: Iterator of record batches
            **kwargs: Additional parameters
        """
        if not self.client:
            self.connect()
        
        mode = kwargs.get("mode", "insert")  # insert | upsert | replace
        upsert_key = kwargs.get("upsert_key", "_id")
        
        try:
            total_loaded = 0
            
            for batch in batches:
                if not batch:
                    continue
                
                if mode == "insert":
                    # Direct insert
                    result = self.collection.insert_many(batch, ordered=False)
                    total_loaded += len(result.inserted_ids)
                
                elif mode == "upsert":
                    # Upsert (update or insert)
                    for record in batch:
                        filter_doc = {upsert_key: record.get(upsert_key)}
                        self.collection.replace_one(filter_doc, record, upsert=True)
                        total_loaded += 1
                
                elif mode == "replace":
                    # Replace collection (delete all + insert)
                    if total_loaded == 0:  # First batch
                        self.collection.delete_many({})
                    result = self.collection.insert_many(batch)
                    total_loaded += len(result.inserted_ids)
                
                logger.debug(f"Loaded batch of {len(batch)} records (total: {total_loaded})")
            
            logger.info(f"Load complete: {total_loaded} records loaded")
            
        except Exception as e:
            logger.error(f"Error during load: {e}")
            raise
    
    def get_schema(self) -> Optional[SchemaDescriptor]:
        """
        Get schema descriptor.
        
        Returns:
            SchemaDescriptor or None
        """
        if self.schema is None:
            self._ensure_schema()
        
        return self.schema
    
    def get_record_count(self) -> int:
        """
        Get total record count in collection.
        
        Returns:
            Number of documents matching filter
        """
        if not self.client:
            self.connect()
        
        return self.collection.count_documents(self.filter)
    
    def validate_schema(self) -> bool:
        """
        Validate actual data against schema.
        
        Returns:
            True if validation passed
        """
        if not self.client:
            self.connect()
        
        self._ensure_schema()
        
        # Sample documents
        sample_docs = list(self.collection.find(self.filter).limit(self.sample_size))
        
        from hydra_etl.internal.schema import SchemaValidator
        validator = SchemaValidator(self.schema, drift_policy=self.drift_policy)
        
        # Validate each document
        all_valid = True
        for doc in sample_docs:
            normalized = self.normalizer.normalize_document(doc)
            result = validator.validate_document(normalized)
            
            if not result.valid:
                all_valid = False
                logger.warning(f"Validation failed: {result.errors}")
        
        return all_valid