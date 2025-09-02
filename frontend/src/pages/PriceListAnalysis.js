import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { apiFetch } from '../utils/api';

const PriceListAnalysis = () => {
    const { token } = useAuth();
    const [tasks, setTasks] = useState([]);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [selectedFile, setSelectedFile] = useState(null);
    const [platform, setPlatform] = useState('autopiter');
    const [competitorBrandFilter, setCompetitorBrandFilter] = useState('');
    const [includePriceAnalysis, setIncludePriceAnalysis] = useState(true);
    const [selectedTask, setSelectedTask] = useState(null);
    const [taskItems, setTaskItems] = useState([]);
    const [currentPage, setCurrentPage] = useState(1);
    const [totalPages, setTotalPages] = useState(1);
    const [error, setError] = useState('');

    const API_BASE = process.env.REACT_APP_API_URL || '/api';

    useEffect(() => {
        loadTasks();
    }, []);

    const loadTasks = async () => {
        try {
            setLoading(true);
            setError('');
            const response = await apiFetch(`${API_BASE}/price-list-tasks/`, {
                headers: {
                    'Content-Type': 'application/json'
                }
            }, token);
            
            if (response.ok) {
                const data = await response.json();
                setTasks(data);
            } else {
                setError('Ошибка загрузки задач');
            }
        } catch (error) {
            console.error('Ошибка загрузки задач:', error);
            setError('Ошибка подключения к серверу');
        } finally {
            setLoading(false);
        }
    };

    const handleFileChange = (event) => {
        const file = event.target.files[0];
        setSelectedFile(file);
        setError('');
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        
        if (!selectedFile) {
            setError('Выберите файл прайс-листа');
            return;
        }

        try {
            setUploading(true);
            setError('');
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('platform', platform);
            formData.append('competitor_brand_filter', competitorBrandFilter);
            formData.append('include_price_analysis', includePriceAnalysis);

            const response = await apiFetch(`${API_BASE}/price-list-tasks/create/`, {
                method: 'POST',
                body: formData
            }, token);

            if (response.ok) {
                const data = await response.json();
                setSelectedFile(null);
                setCompetitorBrandFilter('');
                setError('');
                // Показываем успешное сообщение
                setError('Задача создана успешно!');
                setTimeout(() => setError(''), 3000);
                loadTasks();
                // Сбрасываем форму
                document.getElementById('file-input').value = '';
            } else {
                const errorData = await response.json();
                setError(`Ошибка: ${errorData.error || 'Неизвестная ошибка'}`);
            }
        } catch (error) {
            console.error('Ошибка создания задачи:', error);
            setError('Ошибка создания задачи');
        } finally {
            setUploading(false);
        }
    };

    const loadTaskDetails = async (taskId) => {
        try {
            const response = await apiFetch(`${API_BASE}/price-list-tasks/${taskId}/`, {
                headers: {
                    'Content-Type': 'application/json'
                }
            }, token);
            
            if (response.ok) {
                const data = await response.json();
                setSelectedTask(data);
                loadTaskItems(taskId, 1);
            }
        } catch (error) {
            console.error('Ошибка загрузки деталей задачи:', error);
        }
    };

    const loadTaskItems = async (taskId, page = 1) => {
        try {
            const response = await apiFetch(`${API_BASE}/price-list-tasks/${taskId}/items/?page=${page}&page_size=50`, {
                headers: {
                    'Content-Type': 'application/json'
                }
            }, token);
            
            if (response.ok) {
                const data = await response.json();
                setTaskItems(data.items);
                setCurrentPage(data.pagination.page);
                setTotalPages(data.pagination.total_pages);
            }
        } catch (error) {
            console.error('Ошибка загрузки позиций:', error);
        }
    };

    const downloadResult = async (taskId) => {
        try {
            const response = await apiFetch(`${API_BASE}/price-list-tasks/${taskId}/download/`, {}, token);
            
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `price_list_results_${taskId}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            }
        } catch (error) {
            console.error('Ошибка скачивания:', error);
            setError('Ошибка скачивания файла');
        }
    };

    const deleteTask = async (taskId) => {
        if (!window.confirm('Вы уверены, что хотите удалить эту задачу?')) {
            return;
        }

        try {
            const response = await apiFetch(`${API_BASE}/price-list-tasks/${taskId}/delete/`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            }, token);

            if (response.ok) {
                loadTasks();
                if (selectedTask && selectedTask.id === taskId) {
                    setSelectedTask(null);
                    setTaskItems([]);
                }
                setError('Задача удалена');
                setTimeout(() => setError(''), 3000);
            }
        } catch (error) {
            console.error('Ошибка удаления:', error);
            setError('Ошибка удаления задачи');
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'completed': return 'text-green-600 dark:text-green-400';
            case 'processing': return 'text-blue-600 dark:text-blue-400';
            case 'failed': return 'text-red-600 dark:text-red-400';
            default: return 'text-gray-600 dark:text-gray-400';
        }
    };

    const getStatusBadge = (status) => {
        const colors = {
            'completed': 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
            'processing': 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
            'failed': 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
            'pending': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
        };
        
        const labels = {
            'completed': 'Завершено',
            'processing': 'Выполняется',
            'failed': 'Ошибка',
            'pending': 'В очереди'
        };
        
        return (
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[status] || colors.pending}`}>
                {labels[status] || status}
            </span>
        );
    };

    const getPlatformName = (platform) => {
        const platforms = {
            'autopiter': 'АвтоПитер',
            'emex': 'Емекс',
            'armtek': 'Армтек'
        };
        return platforms[platform] || platform;
    };

    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <div className="container mx-auto px-4 py-8">
                <div className="mb-8">
                    <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
                        Анализ прайс-листа на площадках
                    </h1>
                    <p className="text-gray-600 dark:text-gray-300">
                        Загрузите прайс-лист для проверки наличия позиций на торговых площадках
                    </p>
                </div>
                
                {/* Сообщения об ошибках/успехе */}
                {error && (
                    <div className={`mb-6 p-4 rounded-lg ${error.includes('успешно') 
                        ? 'bg-green-50 border border-green-200 text-green-800 dark:bg-green-900 dark:border-green-700 dark:text-green-200' 
                        : 'bg-red-50 border border-red-200 text-red-800 dark:bg-red-900 dark:border-red-700 dark:text-red-200'
                    }`}>
                        {error}
                    </div>
                )}
                
                {/* Форма загрузки */}
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 mb-8">
                    <div className="flex items-center mb-6">
                        <div className="w-10 h-10 bg-blue-100 dark:bg-blue-900 rounded-lg flex items-center justify-center mr-4">
                            <svg className="w-6 h-6 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                            </svg>
                        </div>
                        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Загрузить прайс-лист</h2>
                    </div>
                    
                    <form onSubmit={handleSubmit} className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Файл прайс-листа (Excel)
                                </label>
                                <input
                                    id="file-input"
                                    type="file"
                                    accept=".xlsx,.xls"
                                    onChange={handleFileChange}
                                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    required
                                />
                                {selectedFile && (
                                    <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                                        Выбран файл: {selectedFile.name}
                                    </p>
                                )}
                            </div>
                            
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Торговая площадка
                                </label>
                                <select
                                    value={platform}
                                    onChange={(e) => setPlatform(e.target.value)}
                                    className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                >
                                    <option value="autopiter">АвтоПитер</option>
                                    <option value="emex">Емекс</option>
                                    <option value="armtek">Армтек</option>
                                </select>
                            </div>
                        </div>
                        
                        <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Фильтр бренда конкурента (необязательно)
                            </label>
                            <input
                                type="text"
                                value={competitorBrandFilter}
                                onChange={(e) => setCompetitorBrandFilter(e.target.value)}
                                placeholder="Например: Ootoko"
                                className="w-full p-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            />
                        </div>
                        
                        <div className="flex items-center">
                            <input
                                type="checkbox"
                                id="includePriceAnalysis"
                                checked={includePriceAnalysis}
                                onChange={(e) => setIncludePriceAnalysis(e.target.checked)}
                                className="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500 dark:focus:ring-blue-600 dark:ring-offset-gray-800 focus:ring-2 dark:bg-gray-700 dark:border-gray-600"
                            />
                            <label htmlFor="includePriceAnalysis" className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                                Включить анализ цен
                            </label>
                        </div>
                        
                        <button
                            type="submit"
                            disabled={uploading || !selectedFile}
                            className="w-full md:w-auto bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white font-medium py-3 px-6 rounded-lg transition-colors duration-200 flex items-center justify-center"
                        >
                            {uploading ? (
                                <>
                                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                                    </svg>
                                    Загрузка...
                                </>
                            ) : (
                                'Создать задачу'
                            )}
                        </button>
                    </form>
                </div>
                
                {/* Список задач */}
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center">
                            <div className="w-10 h-10 bg-green-100 dark:bg-green-900 rounded-lg flex items-center justify-center mr-4">
                                <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                </svg>
                            </div>
                            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Задачи анализа</h2>
                        </div>
                        <button
                            onClick={loadTasks}
                            className="bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 px-4 py-2 rounded-lg transition-colors duration-200"
                        >
                            Обновить
                        </button>
                    </div>
                
                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                        <span className="ml-3 text-gray-600 dark:text-gray-400">Загрузка...</span>
                    </div>
                ) : tasks.length === 0 ? (
                    <div className="text-center py-8">
                        <svg className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                        </svg>
                        <p className="text-gray-500 dark:text-gray-400">Нет задач анализа</p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {tasks.map((task) => (
                            <div key={task.id} className="border border-gray-200 dark:border-gray-700 rounded-lg p-6 hover:shadow-md transition-shadow duration-200">
                                <div className="flex justify-between items-start">
                                    <div className="flex-1">
                                        <div className="flex items-center mb-3">
                                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mr-3">
                                                Задача #{task.id}
                                            </h3>
                                            {getStatusBadge(task.status)}
                                        </div>
                                        
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                                            <div>
                                                <p className="text-gray-600 dark:text-gray-400">
                                                    <span className="font-medium">Площадка:</span> {getPlatformName(task.platform)}
                                                </p>
                                                <p className="text-gray-600 dark:text-gray-400">
                                                    <span className="font-medium">Создана:</span> {new Date(task.created_at).toLocaleString()}
                                                </p>
                                            </div>
                                            {task.processed_items > 0 && (
                                                <div>
                                                    <p className="text-gray-600 dark:text-gray-400">
                                                        <span className="font-medium">Прогресс:</span> {task.processed_items}/{task.total_items}
                                                    </p>
                                                    <p className="text-gray-600 dark:text-gray-400">
                                                        <span className="font-medium">Найдено:</span> {task.found_items} | 
                                                        <span className="font-medium"> Не найдено:</span> {task.not_found_items}
                                                    </p>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    
                                    <div className="flex space-x-2 ml-4">
                                        <button
                                            onClick={() => loadTaskDetails(task.id)}
                                            className="bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                                        >
                                            Детали
                                        </button>
                                        
                                        {task.has_result_file && (
                                            <button
                                                onClick={() => downloadResult(task.id)}
                                                className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                                            >
                                                Скачать
                                            </button>
                                        )}
                                        
                                        <button
                                            onClick={() => deleteTask(task.id)}
                                            className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200"
                                        >
                                            Удалить
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
            
            {/* Детали задачи */}
            {selectedTask && (
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6 mt-8">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                            Детали задачи #{selectedTask.id}
                        </h2>
                        <button
                            onClick={() => setSelectedTask(null)}
                            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                        >
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                    
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        <div className="space-y-3">
                            <p className="text-gray-600 dark:text-gray-400">
                                <span className="font-medium">Площадка:</span> {getPlatformName(selectedTask.platform)}
                            </p>
                            <p className="text-gray-600 dark:text-gray-400">
                                <span className="font-medium">Статус:</span> {getStatusBadge(selectedTask.status)}
                            </p>
                            <p className="text-gray-600 dark:text-gray-400">
                                <span className="font-medium">Создана:</span> {new Date(selectedTask.created_at).toLocaleString()}
                            </p>
                        </div>
                        <div className="space-y-3">
                            <p className="text-gray-600 dark:text-gray-400">
                                <span className="font-medium">Всего позиций:</span> {selectedTask.total_items}
                            </p>
                            <p className="text-gray-600 dark:text-gray-400">
                                <span className="font-medium">Обработано:</span> {selectedTask.processed_items}
                            </p>
                            <div className="flex space-x-4">
                                <p className="text-green-600 dark:text-green-400">
                                    <span className="font-medium">Найдено:</span> {selectedTask.found_items}
                                </p>
                                <p className="text-red-600 dark:text-red-400">
                                    <span className="font-medium">Не найдено:</span> {selectedTask.not_found_items}
                                </p>
                            </div>
                        </div>
                    </div>
                    
                    {selectedTask.log && (
                        <div className="mb-6">
                            <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Лог выполнения:</h3>
                            <div className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg p-4 max-h-60 overflow-y-auto">
                                <pre className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap font-mono">{selectedTask.log}</pre>
                            </div>
                        </div>
                    )}
                    
                    {/* Список позиций */}
                    {taskItems.length > 0 && (
                        <div>
                            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">
                                Позиции ({taskItems.length})
                            </h3>
                            
                            <div className="overflow-x-auto">
                                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                    <thead className="bg-gray-50 dark:bg-gray-700">
                                        <tr>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Бренд</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Артикул</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Наименование</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Наличие</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Наша цена</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-300 uppercase tracking-wider">Мин. цена конкурента</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                        {taskItems.map((item) => (
                                            <tr key={item.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">{item.manufacturer}</td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">{item.article}</td>
                                                <td className="px-6 py-4 text-sm text-gray-900 dark:text-white">{item.nomenclature}</td>
                                                <td className="px-6 py-4 whitespace-nowrap">
                                                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                                        item.is_found 
                                                            ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' 
                                                            : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                                                    }`}>
                                                        {item.is_found ? 'Выгружено' : 'НЕТ'}
                                                    </span>
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                                                    {item.marketplace_price ? `${item.marketplace_price} ₽` : '—'}
                                                </td>
                                                <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                                                    {item.min_competitor_price ? `${item.min_competitor_price} ₽` : '—'}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                            
                            {/* Пагинация */}
                            {totalPages > 1 && (
                                <div className="flex items-center justify-between mt-6">
                                    <div className="flex items-center">
                                        <p className="text-sm text-gray-700 dark:text-gray-300">
                                            Показано <span className="font-medium">{(currentPage - 1) * 50 + 1}</span> до{' '}
                                            <span className="font-medium">{Math.min(currentPage * 50, taskItems.length)}</span> из{' '}
                                            <span className="font-medium">{taskItems.length}</span> результатов
                                        </p>
                                    </div>
                                    <div className="flex space-x-2">
                                        <button
                                            onClick={() => loadTaskItems(selectedTask.id, currentPage - 1)}
                                            disabled={currentPage === 1}
                                            className="relative inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Назад
                                        </button>
                                        <span className="relative inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                                            Страница {currentPage} из {totalPages}
                                        </span>
                                        <button
                                            onClick={() => loadTaskItems(selectedTask.id, currentPage + 1)}
                                            disabled={currentPage === totalPages}
                                            className="relative inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 text-sm font-medium rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                                        >
                                            Вперед
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
        </div>
    );
};

export default PriceListAnalysis;
