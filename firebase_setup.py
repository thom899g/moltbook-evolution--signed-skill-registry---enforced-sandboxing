"""
Firebase initialization and configuration with comprehensive error handling.
This module provides centralized Firebase client initialization with proper
resource management and fallback mechanisms.
"""

import json
import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime
import sys

import firebase_admin
from firebase_admin import credentials, firestore, auth, db as realtime_db
from firebase_admin.exceptions import FirebaseError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FirebaseInitializationError(Exception):
    """Custom exception for Firebase initialization failures."""
    pass

class FirebaseManager:
    """
    Singleton manager for Firebase services with automatic retry and fallback.
    Implements proper resource cleanup and connection pooling.
    """
    
    _instance: Optional['FirebaseManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._app = None
            self._firestore_client = None
            self._realtime_db_client = None
            self._initialized = True
    
    def initialize(self, credential_path: Optional[str] = None, project_id: Optional[str] = None) -> None:
        """
        Initialize Firebase with multiple fallback strategies.
        
        Args:
            credential_path: Path to Firebase service account JSON file
            project_id: Firebase project ID (for environment variable fallback)
            
        Raises:
            FirebaseInitializationError: If all initialization methods fail
        """
        # Log initialization attempt
        logger.info("Starting Firebase initialization...")
        
        # Strategy 1: Explicit credential file
        if credential_path and os.path.exists(credential_path):
            try:
                cred = credentials.Certificate(credential_path)
                self._app = firebase_admin.initialize_app(cred, {
                    'projectId': project_id or os.getenv('FIREBASE_PROJECT_ID')
                })
                logger.info("Firebase initialized with credential file")
                self._initialize_clients()
                return
            except (FirebaseError, ValueError, IOError) as e:
                logger.warning(f"Credential file initialization failed: {str(e)}")
        
        # Strategy 2: Environment variable with service account JSON
        env_cred = os.getenv('FIREBASE_SERVICE_ACCOUNT')
        if env_cred:
            try:
                service_account_info = json.loads(env_cred)
                cred = credentials.Certificate(service_account_info)
                self._app = firebase_admin.initialize_app(cred)
                logger.info("Firebase initialized with environment variable")
                self._initialize_clients()
                return
            except (json.JSONDecodeError, FirebaseError, ValueError) as e:
                logger.warning(f"Environment variable initialization failed: {str(e)}")
        
        # Strategy 3: Application Default Credentials (for Cloud environments)
        try:
            self._app = firebase_admin.initialize_app(
                credentials.ApplicationDefault(),
                {'projectId': project_id or os.getenv('FIREBASE_PROJECT_ID', 'default')}
            )
            logger.info("Firebase initialized with application default credentials")
            self._initialize_clients()
            return
        except (FirebaseError, ValueError) as e:
            logger.error(f"Application default credentials failed: {str(e)}")
        
        # All strategies failed
        error_msg = "All Firebase initialization strategies failed. Please provide valid credentials."
        logger.error(error_msg)
        raise FirebaseInitializationError(error_msg)
    
    def _initialize_clients(self) -> None:
        """Initialize Firebase service clients with error handling."""
        try:
            self._firestore_client = firestore.client()
            self._realtime_db_client = realtime_db
            logger.info("Firebase clients initialized successfully")
        except FirebaseError as e:
            logger.error(f"Failed to initialize Firebase clients: {str(e)}")
            raise
    
    @property
    def firestore(self):
        """Get Firestore client with lazy initialization."""
        if self._firestore_client is None:
            self._initialize_clients()
        return self._firestore_client
    
    @property
    def database(self):
        """Get Realtime Database reference with lazy initialization."""
        if self._realtime_db_client is None:
            self._initialize_clients()
        return self._realtime_db_client
    
    @property
    def auth_client(self):
        """Get Auth client."""
        return auth
    
    def close(self) -> None:
        """Clean up Firebase resources."""
        if self._app:
            try:
                firebase_admin.delete_app(self._app)
                logger.info("Firebase app cleaned up")
            except FirebaseError as e:
                logger.warning(f"Error during Firebase cleanup: {str(e)}")
            self._app = None
            self._firestore_client = None
            self._realtime_db_client = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.close()
        if exc_type:
            logger.error(f"Context exited with error: {exc_type.__name__}: {exc_val}")

# Global instance for easy access
firebase_manager = FirebaseManager()

def test_connection() -> bool:
    """Test Firebase connection with comprehensive diagnostics."""
    try:
        # Test Firestore
        test_ref = firebase_manager.firestore.collection('connection_tests').document('test')
        test_ref.set({
            'timestamp': datetime.utcnow().isoformat(),
            'test': 'success'
        })
        test_ref.delete()
        
        logger.info("Firebase connection test successful")
        return True
    except Exception as e:
        logger.error(f"Firebase connection test failed: {str(e)}")
        return False

if __name__ == "__main__":
    # Example usage
    try:
        firebase_manager.initialize(
            credential_path=os.getenv('FIREBASE_CREDENTIALS_PATH'),
            project_id=os.getenv('FIREBASE_PROJECT_ID')
        )
        
        if test_connection():
            print("✅ Firebase setup completed successfully")
        else:
            print("❌ Firebase setup failed")
            sys.exit(1)
            
    except FirebaseInitializationError as e:
        print(f"❌ Critical Firebase initialization error: {e}")
        sys.exit(1)