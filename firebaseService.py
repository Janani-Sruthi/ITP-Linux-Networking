import firebase_admin
from firebase_admin import credentials, db
from typing import Dict, List, Any, Optional
import os
import time
from datetime import datetime

CACHE_ENABLED = True
CACHE_TTL = 30
CACHE = {
    'normalTests': {'data': None, 'timestamp': 0},
    'emergencyTests': {'data': None, 'timestamp': 0},
    'allTests': {'data': None, 'timestamp': 0},
    'statistics': {'data': None, 'timestamp': 0}
}

def initializeFirebase():
    try:
        if firebase_admin._apps:
            print("✓ Firebase already initialized")
            return True
        
        if not os.path.exists('serviceAccountKey.json'):
            print("❌ Error: serviceAccountKey.json not found!")
            print("   Please place your Firebase service account key in the project root.")
            return False
        
        cred = credentials.Certificate('serviceAccountKey.json')
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://itpproject-2026-default-rtdb.asia-southeast1.firebasedatabase.app/'
        })
        
        print("✓ Firebase Realtime Database initialized successfully")
        return True
        
    except FileNotFoundError:
        print("❌ Error: serviceAccountKey.json file not found")
        print("   Please download your service account key from Firebase Console")
        return False
    except Exception as e:
        print(f"❌ Error initializing Firebase: {e}")
        return False

FIREBASE_READY = initializeFirebase()

def getCached(key: str, ttl: int = CACHE_TTL):
    if not CACHE_ENABLED:
        return None
    
    cacheEntry = CACHE.get(key)
    if not cacheEntry:
        return None
    
    data, timestamp = cacheEntry['data'], cacheEntry['timestamp']
    if data is not None and (time.time() - timestamp) < ttl:
        return data
    
    return None

def setCache(key: str, data: Any):
    if not CACHE_ENABLED:
        return
    
    CACHE[key] = {
        'data': data,
        'timestamp': time.time()
    }

def clearCache():
    for key in CACHE:
        CACHE[key] = {'data': None, 'timestamp': 0}
    print("✓ Cache cleared")

class NetworkDataGetter:
    
    def __init__(self):
        self.normalRef = db.reference('normal') if FIREBASE_READY else None
        self.emergencyRef = db.reference('emergency') if FIREBASE_READY else None
        self.isConnected = FIREBASE_READY
        
        if not self.isConnected:
            print("⚠️ Warning: Firebase not connected. Some functions may fail.")
    
    def _checkConnection(self) -> bool:
        if not self.isConnected:
            print("❌ Firebase not connected. Please check your credentials.")
            return False
        return True
    
    def getNormalTests(self, useCache: bool = True, limit: int = None) -> List[Dict[str, Any]]:
        if not self._checkConnection():
            return []
        
        if useCache:
            cached = getCached('normalTests')
            if cached is not None:
                return cached[:limit] if limit else cached
        
        try:
            testsData = self.normalRef.get()
            
            if not testsData:
                print("ℹ️ No normal test data found in Firebase")
                return []
            
            tests = []
            for testId, testDetails in testsData.items():
                if isinstance(testDetails, dict):
                    testDetails['_key'] = testId
                    testDetails['_type'] = 'normal'
                    tests.append(testDetails)
            
            tests.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            setCache('normalTests', tests)
            
            print(f"✓ Loaded {len(tests)} normal tests")
            return tests[:limit] if limit else tests
            
        except Exception as e:
            print(f"❌ Error getting normal tests: {e}")
            return []
    
    def getEmergencyTests(self, useCache: bool = True, limit: int = None) -> List[Dict[str, Any]]:
        if not self._checkConnection():
            return []
        
        if useCache:
            cached = getCached('emergencyTests')
            if cached is not None:
                return cached[:limit] if limit else cached
        
        try:
            testsData = self.emergencyRef.get()
            
            if not testsData:
                print("ℹ️ No emergency test data found in Firebase")
                return []
            
            tests = []
            for testId, testDetails in testsData.items():
                if isinstance(testDetails, dict):
                    testDetails['_key'] = testId
                    testDetails['_type'] = 'emergency'
                    tests.append(testDetails)
            
            tests.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            setCache('emergencyTests', tests)
            
            print(f"✓ Loaded {len(tests)} emergency tests")
            return tests[:limit] if limit else tests
            
        except Exception as e:
            print(f"❌ Error getting emergency tests: {e}")
            return []
    
    def getAllTests(self, useCache: bool = True, limit: int = None) -> List[Dict[str, Any]]:
        if not self._checkConnection():
            return []
        
        if useCache:
            cached = getCached('allTests')
            if cached is not None:
                return cached[:limit] if limit else cached
        
        try:
            normalTests = self.getNormalTests(useCache=False)
            emergencyTests = self.getEmergencyTests(useCache=False)
            
            allTests = normalTests + emergencyTests
            allTests.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            setCache('allTests', allTests)
            
            print(f"✓ Loaded {len(allTests)} total tests ({len(normalTests)} normal, {len(emergencyTests)} emergency)")
            return allTests[:limit] if limit else allTests
            
        except Exception as e:
            print(f"❌ Error getting all tests: {e}")
            return []
    
    def getLatestNormalTest(self) -> Optional[Dict[str, Any]]:
        tests = self.getNormalTests(limit=1)
        return tests[0] if tests else None
    
    def getLatestEmergencyTest(self) -> Optional[Dict[str, Any]]:
        tests = self.getEmergencyTests(limit=1)
        return tests[0] if tests else None
    
    def getLatestTest(self) -> Optional[Dict[str, Any]]:
        tests = self.getAllTests(limit=1)
        return tests[0] if tests else None
    
    def getTestStatistics(self, useCache: bool = True) -> Dict[str, Any]:
        if not self._checkConnection():
            return self._emptyStatistics()
        
        if useCache:
            cached = getCached('statistics')
            if cached is not None:
                return cached
        
        try:
            normalTests = self.getNormalTests(useCache=False)
            emergencyTests = self.getEmergencyTests(useCache=False)
            
            normalTotal = len(normalTests)
            normalSuccess = len([t for t in normalTests if t.get('status') == 'success'])
            normalFailed = len([t for t in normalTests if t.get('status') == 'failed'])
            
            emergencyTotal = len(emergencyTests)
            emergencySuccess = len([t for t in emergencyTests if t.get('status') == 'success'])
            emergencyFailed = len([t for t in emergencyTests if t.get('status') == 'failed'])
            
            totalTests = normalTotal + emergencyTotal
            totalSuccess = normalSuccess + emergencySuccess
            totalFailed = normalFailed + emergencyFailed
            
            latestNormal = self.getLatestNormalTest()
            latestEmergency = self.getLatestEmergencyTest()
            latestTest = self.getLatestTest()
            
            stats = {
                'totalTests': totalTests,
                'totalSuccess': totalSuccess,
                'totalFailed': totalFailed,
                'successRate': round((totalSuccess / totalTests * 100) if totalTests > 0 else 0, 1),
                'normal': {
                    'total': normalTotal,
                    'success': normalSuccess,
                    'failed': normalFailed,
                    'latestSpeed': latestNormal.get('speed', 'N/A') if latestNormal else 'N/A',
                    'latestTimestamp': latestNormal.get('timestamp') if latestNormal else None,
                    'lastUpdated': latestNormal.get('timestamp') if latestNormal else None
                },
                'emergency': {
                    'total': emergencyTotal,
                    'success': emergencySuccess,
                    'failed': emergencyFailed,
                    'latestSpeed': latestEmergency.get('speed', 'N/A') if latestEmergency else 'N/A',
                    'latestTimestamp': latestEmergency.get('timestamp') if latestEmergency else None,
                    'lastUpdated': latestEmergency.get('timestamp') if latestEmergency else None
                },
                'latestTest': {
                    'type': latestTest.get('_type', 'N/A') if latestTest else 'N/A',
                    'speed': latestTest.get('speed', 'N/A') if latestTest else 'N/A',
                    'status': latestTest.get('status', 'N/A') if latestTest else 'N/A',
                    'timestamp': latestTest.get('timestamp') if latestTest else None,
                    'port': latestTest.get('port') if latestTest else None
                },
                'timestamp': datetime.now().isoformat()
            }
            
            setCache('statistics', stats)
            
            print(f"✓ Generated test statistics: {totalTests} total tests")
            return stats
            
        except Exception as e:
            print(f"❌ Error getting test statistics: {e}")
            return self._emptyStatistics()
    
    def _emptyStatistics(self) -> Dict[str, Any]:
        return {
            'totalTests': 0,
            'totalSuccess': 0,
            'totalFailed': 0,
            'successRate': 0,
            'normal': {
                'total': 0,
                'success': 0,
                'failed': 0,
                'latestSpeed': 'N/A',
                'latestTimestamp': None,
                'lastUpdated': None
            },
            'emergency': {
                'total': 0,
                'success': 0,
                'failed': 0,
                'latestSpeed': 'N/A',
                'latestTimestamp': None,
                'lastUpdated': None
            },
            'latestTest': {
                'type': 'N/A',
                'speed': 'N/A',
                'status': 'N/A',
                'timestamp': None,
                'port': None
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def addNormalTest(self, testData: Dict[str, Any]) -> Optional[str]:
        if not self._checkConnection():
            return None
        
        try:
            requiredFields = ['id', 'timestamp', 'host', 'port', 'status']
            for field in requiredFields:
                if field not in testData:
                    print(f"❌ Missing required field: {field}")
                    return None
            
            newRef = self.normalRef.push(testData)
            
            clearCache()
            
            print(f"✓ Added normal test (ID: {newRef.key}) - Speed: {testData.get('speed', 'N/A')}")
            return newRef.key
            
        except Exception as e:
            print(f"❌ Error adding normal test: {e}")
            return None
    
    def addEmergencyTest(self, testData: Dict[str, Any]) -> Optional[str]:
        if not self._checkConnection():
            return None
        
        try:
            requiredFields = ['id', 'timestamp', 'host', 'port', 'status']
            for field in requiredFields:
                if field not in testData:
                    print(f"❌ Missing required field: {field}")
                    return None
            
            newRef = self.emergencyRef.push(testData)
            
            clearCache()
            
            print(f"✓ Added emergency test (ID: {newRef.key}) - Speed: {testData.get('speed', 'N/A')}")
            return newRef.key
            
        except Exception as e:
            print(f"❌ Error adding emergency test: {e}")
            return None
    
    def getTestsByLaptop(self, laptop_id: str, test_type: str = None, limit: int = None) -> List[Dict[str, Any]]:
        try:
            all_tests = self.getAllTests(limit=None)
            
            filtered = []
            for test in all_tests:
                if test.get('laptop_id') == laptop_id:
                    if test_type is None or test.get('test_type') == test_type:
                        filtered.append(test)
            
            filtered.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return filtered[:limit] if limit else filtered
            
        except Exception as e:
            print(f"❌ Error getting tests by laptop: {e}")
            return []

    def getLaptopStatistics(self) -> Dict[str, Any]:
        """Get statistics per laptop"""
        try:
            all_tests = self.getAllTests(limit=None)
            laptop_stats = {}
            
            for test in all_tests:
                laptop_id = test.get('laptop_id', 'unknown')
                if laptop_id not in laptop_stats:
                    laptop_stats[laptop_id] = {
                        'laptop_id': laptop_id,
                        'laptop_name': test.get('laptop_name', laptop_id),
                        'location': test.get('location', 'Unknown'),
                        'test_type': test.get('test_type', 'unknown'),
                        'port': test.get('port', 0),
                        'total_tests': 0,
                        'successful': 0,
                        'failed': 0,
                        'last_test': None,
                        'last_speed': 'N/A'
                    }
                
                laptop_stats[laptop_id]['total_tests'] += 1
                if test.get('status') == 'success':
                    laptop_stats[laptop_id]['successful'] += 1
                else:
                    laptop_stats[laptop_id]['failed'] += 1
                
                if laptop_stats[laptop_id]['last_test'] is None or test.get('timestamp', '') > laptop_stats[laptop_id]['last_test']:
                    laptop_stats[laptop_id]['last_test'] = test.get('timestamp')
                    laptop_stats[laptop_id]['last_speed'] = test.get('speed', 'N/A')
            
            return laptop_stats
            
        except Exception as e:
            print(f"❌ Error getting laptop statistics: {e}")
            return {}

    def getTestsByPort(self, port: int, limit: int = None) -> List[Dict[str, Any]]:
        """Get tests from a specific port"""
        try:
            all_tests = self.getAllTests(limit=None)
            
            filtered = [t for t in all_tests if t.get('port') == port]
            filtered.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return filtered[:limit] if limit else filtered
            
        except Exception as e:
            print(f"❌ Error getting tests by port: {e}")
            return []

    def getTestsByType(self, test_type: str, limit: int = None) -> List[Dict[str, Any]]:
        """Get tests by type (normal/emergency)"""
        try:
            all_tests = self.getAllTests(limit=None)
            
            filtered = [t for t in all_tests if t.get('_type') == test_type or t.get('test_type') == test_type]
            filtered.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return filtered[:limit] if limit else filtered
            
        except Exception as e:
            print(f"❌ Error getting tests by type: {e}")
            return []

networkData = NetworkDataGetter()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("Testing Firebase Service (matching app.js)")
    print("="*60 + "\n")
    
    if not FIREBASE_READY:
        print("❌ Firebase not initialized. Please check your credentials.")
        print("   Make sure serviceAccountKey.json is in the project root.")
        exit(1)
    
    print("📊 Fetching normal tests (port 8888)...")
    normalTests = networkData.getNormalTests(limit=5)
    print(f"✅ Found {len(normalTests)} normal tests\n")
    
    if normalTests:
        print("📱 Sample normal test:")
        test = normalTests[0]
        print(f"   ID: {test.get('_key')}")
        print(f"   Timestamp: {test.get('timestamp')}")
        print(f"   Host: {test.get('host')}")
        print(f"   Port: {test.get('port')}")
        print(f"   Speed: {test.get('speed')}")
        print(f"   Status: {test.get('status')}")
        print()
    
    print("📊 Fetching emergency tests (port 9999)...")
    emergencyTests = networkData.getEmergencyTests(limit=5)
    print(f"✅ Found {len(emergencyTests)} emergency tests\n")
    
    if emergencyTests:
        print("📱 Sample emergency test:")
        test = emergencyTests[0]
        print(f"   ID: {test.get('_key')}")
        print(f"   Timestamp: {test.get('timestamp')}")
        print(f"   Host: {test.get('host')}")
        print(f"   Port: {test.get('port')}")
        print(f"   Speed: {test.get('speed')}")
        print(f"   Status: {test.get('status')}")
        print()
    
    print("📈 Statistics:")
    stats = networkData.getTestStatistics()
    print(f"   Total Tests: {stats['totalTests']}")
    print(f"   Success Rate: {stats['successRate']}%")
    print(f"   Normal Tests: {stats['normal']['total']}")
    print(f"   Emergency Tests: {stats['emergency']['total']}")
    print(f"   Latest Test Type: {stats['latestTest']['type']}")
    print(f"   Latest Test Speed: {stats['latestTest']['speed']}")
    
    print("\n✅ Firebase Service test complete!")