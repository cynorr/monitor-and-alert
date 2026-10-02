export async function post(resource, payload, signal) {
    const response = await fetch('/v1/' + resource, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal });
    const data = await response.json();
    if (!response.ok)
        throw new Error(data.error ?? 'Request failed');
    return data;
}
