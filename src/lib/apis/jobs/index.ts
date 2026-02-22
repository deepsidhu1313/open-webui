import { WEBUI_API_BASE_URL } from '$lib/constants';

export const getJobs = async (token: string, skip = 0, limit = 20) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs?skip=${skip}&limit=${limit}`, {
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

export const getJob = async (token: string, jobId: string) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/${jobId}`, {
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

export const cancelJob = async (token: string, jobId: string) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/${jobId}`, {
        method: 'DELETE',
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

export const submitJob = async (token: string, body: object) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/chat/completions`, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
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

// ---------------------------------------------------------------------------
// Archive API
// ---------------------------------------------------------------------------

export const getArchivedJobs = async (
    token: string,
    skip = 0,
    limit = 50,
    status?: string,
    model_id?: string
) => {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (status) params.set('status', status);
    if (model_id) params.set('model_id', model_id);
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/archive?${params}`, {
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

export const getArchiveConfig = async (token: string) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/archive/config`, {
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

export const runArchiveSweep = async (token: string) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/archive/run`, {
        method: 'POST',
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



// ---------------------------------------------------------------------------
// A3: Admin retry
// ---------------------------------------------------------------------------

export const retryJob = async (token: string, jobId: string) => {
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/${jobId}/retry`, {
        method: 'POST',
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

// ---------------------------------------------------------------------------
// A4: Admin job list with filters
// ---------------------------------------------------------------------------

export const getAdminJobs = async (
    token: string,
    skip = 0,
    limit = 50,
    status?: string,
    model_id?: string,
    user_id?: string
) => {
    const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
    if (status) params.set('status', status);
    if (model_id) params.set('model_id', model_id);
    if (user_id) params.set('user_id', user_id);
    const res = await fetch(`${WEBUI_API_BASE_URL}/jobs/admin/list?${params}`, {
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

// ---------------------------------------------------------------------------
// B4: Analytics CSV export — returns raw Response for blob extraction
// ---------------------------------------------------------------------------

export const getJobAnalyticsExport = async (token: string): Promise<Response | null> => {
    try {
        return await fetch(`${WEBUI_API_BASE_URL}/jobs/analytics/export`, {
            headers: { Authorization: `Bearer ${token}` }
        });
    } catch (err) {
        console.error(err);
        return null;
    }
};
