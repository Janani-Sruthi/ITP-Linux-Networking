from flask import Flask, jsonify, render_template, request, redirect, url_for
from firebaseService import networkData
import os
from datetime import datetime

app = Flask(__name__)

# ========== MAIN ROUTES ==========

@app.route('/')
def index():
    """Combined dashboard with tabs"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """Redirect to combined"""
    return render_template('index.html')

# ========== API ROUTES ==========

@app.route('/api/tests')
def apiGetAllTests():
    try:
        limit = request.args.get('limit', default=None, type=int)
        tests = networkData.getAllTests(limit=limit)
        
        normalCount = 0
        emergencyCount = 0
        for test in tests:
            if test.get('_type') == 'normal':
                normalCount += 1
            elif test.get('_type') == 'emergency':
                emergencyCount += 1
        
        return jsonify({
            'success': True,
            'data': tests,
            'count': len(tests),
            'normalCount': normalCount,
            'emergencyCount': emergencyCount,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        app.logger.error(f"Error in API: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

#=============API for laptops and tests============

@app.route('/api/laptops')
def apiGetLaptops():
    """Get list of all laptops that have sent data"""
    try:
        stats = networkData.getLaptopStatistics()
        return jsonify({
            'success': True,
            'data': list(stats.values()),
            'count': len(stats),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        app.logger.error(f"Error getting laptops: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/laptops/<laptop_id>/tests')
def apiGetLaptopTests(laptop_id):
    """Get tests from a specific laptop"""
    try:
        limit = request.args.get('limit', default=50, type=int)
        tests = networkData.getTestsByLaptop(laptop_id, None, limit)
        return jsonify({
            'success': True,
            'data': tests,
            'count': len(tests),
            'laptop_id': laptop_id,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        app.logger.error(f"Error getting laptop tests: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tests/port/<int:port>')
def apiGetTestsByPort(port):
    """Get tests from a specific port"""
    try:
        limit = request.args.get('limit', default=50, type=int)
        tests = networkData.getTestsByPort(port, limit)
        return jsonify({
            'success': True,
            'data': tests,
            'count': len(tests),
            'port': port,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        app.logger.error(f"Error getting tests by port: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/tests/type/<test_type>')
def apiGetTestsByType(test_type):
    """Get tests by type (normal/emergency)"""
    try:
        limit = request.args.get('limit', default=50, type=int)
        tests = networkData.getTestsByType(test_type, limit)
        return jsonify({
            'success': True,
            'data': tests,
            'count': len(tests),
            'test_type': test_type,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        app.logger.error(f"Error getting tests by type: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ========== RUN APP ==========

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    DEBUG_MODE = False
    
    print("=" * 50)
    print("Starting OptiFlow")
    print(f"Mode: {'Development' if DEBUG_MODE else 'Production'}")
    print(f"URL: http://localhost:{port}")
    print("=" * 50)
    
    app.run(
        debug=DEBUG_MODE,
        host='0.0.0.0',
        port=port,
        threaded=True
    )