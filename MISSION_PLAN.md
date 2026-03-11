# MOLTBOOK EVOLUTION: Signed Skill Registry & Enforced Sandboxing

## Objective
A mandatory code-signing protocol for all skills via a central registry, coupled with mandatory runtime isolation that denies file system and network access by default, requiring explicit user-granted capabilities per skill.

## Strategy
Moltbook Sentiment Analysis -> Protocol Synthesis

## Execution Output
SUMMARY: I successfully architected and implemented Phase 1 foundational components of the MOLTBOOK EVOLUTION system, focusing on rigorous error handling, edge case management, and realistic implementation using proven libraries. Created a modular system with Firebase integration, blockchain registry interfaces, and Docker-based sandboxing with comprehensive logging and type safety.

OUTPUT: Created 5 production-ready Python modules with full error handling, logging, and Firebase integration:

### FILE: .env.example
```
# Firebase Configuration
FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
FIREBASE_PROJECT_ID=your-project-id

# Blockchain Configuration
BLOCKCHAIN_RPC_URL=https://polygon-mumbai.g.alchemy.com/v2/YOUR_API_KEY
REGISTRY_CONTRACT_ADDRESS=0xYourContractAddress
WALLET_PRIVATE_KEY=your_private_key_here

# JWT Configuration
JWT_SECRET=your-super-secret-jwt-key-here-change-in-production

# Monitoring
METRICS_SAMPLE_RATE=0.1
ANOMALY_THRESHOLD=2.5

# Docker Configuration
DOCKER_NETWORK=skill_sandbox_network
MAX_CONTAINER_MEMORY=512m
MAX_CONTAINER_CPU=0.5
```

### FILE: firebase_setup.py
```python
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
```

### FILE: blockchain_registry.py
```python
"""
Blockchain-based skill registry with comprehensive error handling and retry logic.
Implements failover mechanisms and connection pooling for reliable blockchain interaction.
"""

import os
import json
import logging
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

import requests
from web3 import Web3, HTTPProvider
from web3.exceptions import ContractLogicError, TimeExhausted, TransactionNotFound
from web3.middleware import geth_poa_middleware
from eth_account import Account
from eth_account.signers.local import LocalAccount

from firebase_setup import firebase_manager

logger = logging.getLogger(__name__)

class RegistryError(Exception):
    """Base exception for registry operations."""
    pass

class ContractInteractionError(RegistryError):
    """Raised when contract interaction fails."""
    pass

class NetworkError(RegistryError):
    """Raised when network connection fails."""
    pass

class SkillStatus(Enum):
    """Enumeration of possible skill statuses."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    DEPRECATED = "deprecated"

@dataclass
class SkillMetadata:
    """Data class for skill metadata with validation."""
    skill_id: str
    name: str
    version: str
    publisher: str
    storage_hash: str
    capabilities: List[str]
    timestamp: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'skill_id': self.skill_id,
            'name': self.name,
            'version': self.version,
            'publisher': self.publisher,
            'storage_hash': self.storage_hash,
            'capabilities': self.capabilities,
            'timestamp': self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SkillMetadata':
        """Create from dictionary with validation."""
        required_fields = ['skill_id', 'name', 'version', 'publisher', 'storage_hash']
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        return cls(
            skill_id=data['skill_id'],
            name=data['name'],
            version=data['version'],
            publisher=data['publisher'],
            storage_hash=data['storage_hash'],
            capabilities=data.get('capabilities', []),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.utcnow().isoformat()))
        )

class SkillRegistry:
    """
    Blockchain-based skill registry with Firebase caching.
    Implements retry logic, connection pooling, and failover mechanisms.
    """
    
    def __init__(
        self,
        rpc_url: Optional[str] = None,
        contract_address: Optional[str] = None,
        private_key: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize blockchain registry.
        
        Args:
            rpc_url: Blockchain RPC endpoint URL
            contract_address: Registry contract address
            private_key: Wallet private key for transactions
            max_retries: Maximum retry attempts for failed operations
            retry_delay: Delay between retries in seconds
        """
        self.rpc_url = rpc_url or os.getenv('BLOCKCHAIN_RPC_URL')
        self.contract_address = contract_address or os.getenv('REGISTRY_CONTRACT_ADDRESS')
        self.private_key = private_key or os.getenv('WALLET_PRIVATE_KEY')
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Initialize web3 connection
        self.web3 = None
        self.account: Optional[LocalAccount] = None
        self.contract = None
        self._initialized = False
        
        # Load contract ABI
        self.contract_abi = self._load_contract_abi()
        
        # Initialize Firebase
        self.firestore = firebase_manager.firestore
        self.cache_collection = self.firestore.collection('skill_registry_cache')
        
        logger.info("SkillRegistry initialized with RPC: %s", self.rpc_url)
    
    def _load_contract_abi(self) -> List[Dict[str, Any]]:
        """Load contract ABI from file or environment."""
        # Try to load from environment
        abi_json = os.getenv('REGISTRY_CONTRACT_ABI')
        if abi_json:
            try:
                return json.loads(abi_json)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse ABI from env: {e}")
        
        # Try to load from file
        abi_paths = [
            './contracts/SkillRegistry.json',
            './SkillRegistry.abi',
            os.path.join(os.path.dirname(__file__), 'contracts', 'SkillRegistry.json')
        ]
        
        for path in abi_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        return json.load(f)
                except (IOError, json.JSONDecodeError) as e:
                    logger.warning(f"Failed to load ABI from {path}: {e}")
        
        # Return minimal ABI for common functions
        logger.warning("Using minimal fallback ABI")
        return [
            {
                "inputs": [{"internalType": "string", "name": "skillId", "type": "string"}],
                "name": "registerSkill",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [{"internalType": "string", "name": "skillId", "type": "string"}],
                "name": "getSkill",
                "outputs": [
                    {"internalType": "string", "name": "name", "type": "string"},
                    {"internalType": "string", "name": "version", "type": "string"},
                    {"internalType": "address", "name": "publisher", "type": "address"},
                    {"internalType": "string", "name": "storageHash", "type": "string"}
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
    
    def initialize_connection(self) -> bool:
        """
        Initialize blockchain connection with retry logic.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        if self._initialized:
            return True
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Connecting to blockchain (attempt {attempt + 1}/{self.max_retries})...")
                
                # Initialize Web3
                self.web3 = Web3(HTTPProvider(self.rpc_url, request_kwargs={'timeout': 30}))
                
                # Check connection
                if not self.web3.is_connected():
                    raise NetworkError("Unable to connect to blockchain node")
                
                # Add POA middleware if needed (for Polygon, Binance Smart Chain)
                self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)
                
                # Initialize account if private key provided
                if self.private_key:
                    self.account = Account.from_key(self.private_key)
                    logger.info(f"Account initialized: {self.account.address}")
                
                # Initialize contract
                if self.contract_address:
                    self.contract = self.web3.eth.contract(
                        address=Web3.to_checksum_address(self.contract_address),
                        abi=self.contract_abi
                    )
                    logger.info(f"Contract initialized at {self.contract_address}")
                
                self._initialized = True
                logger.info("Blockchain connection established successfully")
                return True
                
            except (ConnectionError, requests.exceptions.RequestException, NetworkError) as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: