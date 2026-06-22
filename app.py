#!/usr/bin/env python3
"""
Call Option Analyzer - backend server.
Deploy to Railway. Serves options data via yfinance.
"""
import os
try:
    import yfinance as yf
    from flask import Flask, jsonify
    from flask_cors import CORS
except ImportError:
    print("\n  Missing dependencies. Run:\n  pip install yfinance flask flask-cors\n")
    raise

app = Flask(__name__)
CORS(app)  # Allow all origins (Cloudflare Pages, local dev, etc.)

def safe_float(val, default=0.0):
    try:
        v = float(val)
        return default if (v != v) else v
    except (TypeError, ValueError):
        return default

def safe_int(val, default=0):
    try:
        v = float(val)
        return default if (v != v) else int(v)
    except (TypeError, ValueError):
        return default

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'service': 'Call Option Analyzer API'})

@app.route('/quote/<ticker>')
def quote(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info
        price = info.get('regularMarketPrice') or info.get('currentPrice') or info.get('previousClose')
        prev  = info.get('regularMarketPreviousClose') or info.get('previousClose') or price
        if not price:
            return jsonify({'error': 'No price data found for ' + ticker}), 404
        return jsonify({
            'price': safe_float(price),
            'prev':  safe_float(prev),
            'name':  info.get('longName') or info.get('shortName') or ticker.upper(),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chain/<ticker>')
def chain(ticker):
    try:
        t = yf.Ticker(ticker.upper())
        dates = list(t.options)
        if not dates:
            return jsonify({'error': 'No options found for ' + ticker}), 404
        return jsonify({'expirations': dates})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chain/<ticker>/<expiry>')
def chain_date(ticker, expiry):
    try:
        t = yf.Ticker(ticker.upper())
        opt = t.option_chain(expiry)
        calls = opt.calls
        rows = []
        for _, r in calls.iterrows():
            rows.append({
                'strike':            safe_float(r.get('strike')),
                'lastPrice':         safe_float(r.get('lastPrice')),
                'bid':               safe_float(r.get('bid')),
                'ask':               safe_float(r.get('ask')),
                'volume':            safe_int(r.get('volume')),
                'openInterest':      safe_int(r.get('openInterest')),
                'impliedVolatility': safe_float(r.get('impliedVolatility')),
                'inTheMoney':        bool(r.get('inTheMoney', False)),
            })
        return jsonify({'calls': rows})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8765))
    debug = os.environ.get('FLASK_ENV') == 'development'
    print(f'\n  Starting on port {port}...\n')
    app.run(host='0.0.0.0', port=port, debug=debug)
