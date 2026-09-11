"""
MongoDB query builder.

Constructs optimized MongoDB queries with projection, filtering, and pagination.
"""

from typing import Dict, List, Any, Optional


class QueryBuilder:
    """
    Builds MongoDB queries with projections and filters.
    
    Examples:
        builder = QueryBuilder()
        
        # Simple query
        query = builder.build(collection="users", filter={"active": True})
        
        # With projection (select specific fields)
        query = builder.build(
            collection="users",
            filter={"age": {"$gte": 18}},
            projection=["name", "email", "age"]
        )
        
        # With nested field projection
        query = builder.build(
            collection="orders",
            projection=["order_id", "customer.name", "total"]
        )
    """
    
    def __init__(self):
        """Initialize query builder."""
        pass
    
    def build(
        self,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[List[str]] = None,
        sort: Optional[List[tuple]] = None,
        limit: Optional[int] = None,
        skip: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Build a MongoDB query.
        
        Args:
            collection: Collection name
            filter: MongoDB filter document (e.g., {"age": {"$gte": 18}})
            projection: List of fields to include
            sort: List of (field, direction) tuples
            limit: Maximum number of documents
            skip: Number of documents to skip
            
        Returns:
            Dictionary with query components
        """
        query = {
            "collection": collection,
            "filter": filter or {},
        }
        
        # Build projection
        if projection:
            query["projection"] = self._build_projection(projection)
        
        # Add sort
        if sort:
            query["sort"] = sort
        
        # Add pagination
        if limit is not None:
            query["limit"] = limit
        if skip is not None:
            query["skip"] = skip
        
        return query
    
    def _build_projection(self, fields: List[str]) -> Dict[str, int]:
        """
        Build MongoDB projection document.
        
        Args:
            fields: List of field paths (can include nested paths)
            
        Returns:
            Projection document (e.g., {"name": 1, "customer.email": 1})
        """
        projection = {}
        
        for field in fields:
            # Handle nested fields
            if "." in field:
                # MongoDB supports nested field projection directly
                projection[field] = 1
            elif field.endswith("[]"):
                # Array field - include the whole array
                projection[field.rstrip("[]")] = 1
            else:
                # Simple field
                projection[field] = 1
        
        # Always exclude _id unless explicitly requested
        if "_id" not in fields:
            projection["_id"] = 0
        
        return projection
    
    def build_aggregation(
        self,
        collection: str,
        pipeline: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Build MongoDB aggregation pipeline.
        
        Args:
            collection: Collection name
            pipeline: List of aggregation stages
            
        Returns:
            Aggregation query
        """
        return {
            "collection": collection,
            "type": "aggregation",
            "pipeline": pipeline
        }
    
    def build_unwind_pipeline(
        self,
        array_field: str,
        preserve_null: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Build pipeline to unwind (explode) an array field.
        
        Args:
            array_field: Name of array field to unwind
            preserve_null: Keep documents without the array field
            
        Returns:
            Aggregation pipeline stages
        """
        return [
            {
                "$unwind": {
                    "path": f"${array_field}",
                    "preserveNullAndEmptyArrays": preserve_null
                }
            }
        ]
    
    def build_flatten_pipeline(
        self,
        nested_fields: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """
        Build pipeline to flatten nested fields.
        
        Args:
            nested_fields: Mapping of output_name -> nested_path
                          (e.g., {"customer_name": "customer.name"})
            
        Returns:
            Aggregation pipeline stages
        """
        project_stage = {}
        
        for output_name, nested_path in nested_fields.items():
            project_stage[output_name] = f"${nested_path}"
        
        return [{"$project": project_stage}]
    
    def optimize_projection(
        self,
        required_fields: List[str],
        available_indexes: List[str]
    ) -> Dict[str, int]:
        """
        Optimize projection based on available indexes.
        
        Args:
            required_fields: Fields needed in output
            available_indexes: Indexed fields in collection
            
        Returns:
            Optimized projection
        """
        # Start with required fields
        projection = {field: 1 for field in required_fields}
        
        # Exclude _id if not needed
        if "_id" not in required_fields:
            projection["_id"] = 0
        
        return projection
    
    def build_batched_query(
        self,
        collection: str,
        filter: Dict[str, Any],
        batch_size: int,
        sort_field: str = "_id"
    ) -> Dict[str, Any]:
        """
        Build query for batched extraction.
        
        Args:
            collection: Collection name
            filter: Base filter
            batch_size: Documents per batch
            sort_field: Field to sort by for consistent batching
            
        Returns:
            Query with batching parameters
        """
        return {
            "collection": collection,
            "filter": filter,
            "sort": [(sort_field, 1)],  # 1 = ascending
            "batch_size": batch_size,
            "batched": True
        }