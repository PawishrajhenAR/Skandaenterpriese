/**
 * API client for Skanda backend.
 * Uses configurable API_BASE from config.js.
 * All requests include credentials for session cookies.
 */
(function() {
    'use strict';
    
    function getBase() {
        const params = new URLSearchParams(window.location.search);
        const override = params.get('api');
        if (override) return override.replace(/\/$/, '');
        return (window.API_BASE || '').replace(/\/$/, '');
    }
    
    function apiUrl(path) {
        const base = getBase();
        const p = path.startsWith('/') ? path : '/' + path;
        return base + (p.startsWith('/api') ? p : '/api' + p);
    }
    
    async function request(method, path, body, headers) {
        const url = apiUrl(path);
        const opts = {
            method: method || 'GET',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                ...(headers || {})
            }
        };
        if (body && method !== 'GET') {
            opts.body = typeof body === 'string' ? body : JSON.stringify(body);
        }
        const res = await fetch(url, opts);
        const text = await res.text();
        let data;
        try {
            data = text ? JSON.parse(text) : null;
        } catch (e) {
            data = { error: text || 'Invalid response' };
        }
        if (!res.ok) {
            const err = new Error(data.error || data.message || `HTTP ${res.status}`);
            err.status = res.status;
            err.data = data;
            throw err;
        }
        return data;
    }
    
    window.api = {
        get: (path) => request('GET', path),
        post: (path, body) => request('POST', path, body),
        put: (path, body) => request('PUT', path, body),
        delete: (path) => request('DELETE', path),
        url: apiUrl,
        base: getBase
    };
})();
