export const apiFetch = async (url, options = {}, token) => {
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Token ${token}`);
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    try { localStorage.removeItem('token'); } catch (_) {}
    if (typeof window !== 'undefined') window.location.href = '/login';
    const error = new Error('Unauthorized');
    error.status = 401;
    throw error;
  }
  return response;
};
