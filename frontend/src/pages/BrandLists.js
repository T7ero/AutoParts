import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const GROUP_LABELS = {
  armtek: 'Armtek',
  blacklist: 'Чёрные списки',
};

function BrandLists() {
  const [lists, setLists] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [items, setItems] = useState([]);
  const [text, setText] = useState('');
  const [meta, setMeta] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const token = localStorage.getItem('token');
  const headers = { Authorization: `Token ${token}` };

  const loadOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get('/api/brand-lists/', { headers });
      setLists(res.data);
      if (res.data.length && !selectedId) {
        setSelectedId(res.data[0].id);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Не удалось загрузить списки');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadList = useCallback(async (listId) => {
    if (!listId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`/api/brand-lists/${listId}/`, { headers });
      setMeta(res.data);
      setItems(res.data.items || []);
      setText((res.data.items || []).join('\n'));
    } catch (err) {
      setError(err.response?.data?.error || 'Не удалось загрузить список');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (selectedId) {
      loadList(selectedId);
    }
  }, [selectedId, loadList]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
      const res = await axios.put(
        `/api/brand-lists/${selectedId}/`,
        { items: lines },
        { headers }
      );
      setItems(lines);
      setMessage(`Сохранено: ${res.data.count} записей`);
      loadOverview();
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    setUploading(true);
    setMessage(null);
    setError(null);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await axios.post(
        `/api/brand-lists/${selectedId}/upload/`,
        formData,
        { headers: { ...headers, 'Content-Type': 'multipart/form-data' } }
      );
      setMessage(`Файл загружен: ${res.data.count} записей`);
      loadList(selectedId);
      loadOverview();
    } catch (err) {
      setError(err.response?.data?.error || 'Ошибка загрузки файла');
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const groupedLists = lists.reduce((acc, item) => {
    const group = item.group || 'other';
    if (!acc[group]) acc[group] = [];
    acc[group].push(item);
    return acc;
  }, {});

  return (
    <div className="max-w-6xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Управление списками брендов
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Редактируйте списки брендов Armtek и чёрные списки Autopiter/Emex без изменения кода.
          Одна запись на строку. Строки, начинающиеся с #, игнорируются.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/30 p-4 text-red-700 dark:text-red-300">
          {error}
        </div>
      )}
      {message && (
        <div className="mb-4 rounded-md bg-green-50 dark:bg-green-900/30 p-4 text-green-700 dark:text-green-300">
          {message}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1">
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
            <h2 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
              Списки
            </h2>
            {Object.entries(groupedLists).map(([group, groupItems]) => (
              <div key={group} className="mb-4">
                <p className="text-xs uppercase tracking-wide text-gray-400 mb-2">
                  {GROUP_LABELS[group] || group}
                </p>
                <ul className="space-y-1">
                  {groupItems.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedId(item.id)}
                        className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                          selectedId === item.id
                            ? 'bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200'
                            : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                        }`}
                      >
                        <span className="block font-medium">{item.title}</span>
                        <span className="text-xs text-gray-500">{item.count} записей</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>

        <div className="lg:col-span-3">
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
            {meta ? (
              <>
                <h2 className="text-lg font-medium text-gray-900 dark:text-white">
                  {meta.title}
                </h2>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  {meta.description}
                </p>
                <p className="mt-1 text-xs text-gray-400">
                  Файл: {meta.file || `config/lists/${selectedId}.txt`}
                </p>

                <div className="mt-4">
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    rows={20}
                    className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 font-mono text-sm p-3 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Одна запись на строку&#10;QUNZE&#10;NIPPON&#10;# комментарий"
                    disabled={loading}
                  />
                  <p className="mt-1 text-xs text-gray-400">
                    {text.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#')).length} записей в редакторе
                  </p>
                </div>

                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={handleSave}
                    disabled={saving || loading}
                    className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
                  >
                    {saving ? 'Сохранение...' : 'Сохранить'}
                  </button>

                  <label className="rounded-md bg-gray-600 px-4 py-2 text-sm font-semibold text-white hover:bg-gray-500 cursor-pointer disabled:opacity-50">
                    {uploading ? 'Загрузка...' : 'Загрузить из файла'}
                    <input
                      type="file"
                      accept=".txt,.csv,.list"
                      onChange={handleUpload}
                      disabled={uploading || loading}
                      className="hidden"
                    />
                  </label>

                  <button
                    type="button"
                    onClick={() => loadList(selectedId)}
                    disabled={loading}
                    className="rounded-md border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    Отменить изменения
                  </button>
                </div>
              </>
            ) : (
              <p className="text-gray-500">Выберите список слева</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default BrandLists;
