import { WEBUI_API_BASE_URL } from '$lib/constants';

export const getSystemMetrics = async (token: string) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/system/metrics`, {
        headers: { Authorization: `Bearer ${token}` }
    })
        .then(async (r) => {
            if (!r.ok) throw await r.json();
            return r.json();
        })
        .catch((err) => {
            console.error(err);
            return null;
        });
    return res;
};

export const getServerStats = async (token: string) => {
    const res = await fetch(`/ollama/api/server-stats`, {
        headers: { Authorization: `Bearer ${token}` }
    })
        .then(async (r) => {
            if (!r.ok) throw await r.json();
            return r.json();
        })
        .catch((err) => {
            console.error(err);
            return null;
        });
    return res;
};
