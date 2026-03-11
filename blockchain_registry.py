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