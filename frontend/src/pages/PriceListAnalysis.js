import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

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

    const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

    useEffect(() => {
        loadTasks();
    }, []);

    const loadTasks = async () => {
        try {
            setLoading(true);
            const response = await fetch(`${API_BASE}/price-list-tasks/`, {
                headers: {
                    'Authorization': `Token ${token}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                setTasks(data);
            }
        } catch (error) {
            console.error('Ошибка загрузки задач:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleFileChange = (event) => {
        setSelectedFile(event.target.files[0]);
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        
        if (!selectedFile) {
            alert('Выберите файл прайс-листа');
            return;
        }

        try {
            setUploading(true);
            
            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('platform', platform);
            formData.append('competitor_brand_filter', competitorBrandFilter);
            formData.append('include_price_analysis', includePriceAnalysis);

            const response = await fetch(`${API_BASE}/price-list-tasks/create/`, {
                method: 'POST',
                headers: {
                    'Authorization': `Token ${token}`
                },
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                alert('Задача создана успешно!');
                setSelectedFile(null);
                setCompetitorBrandFilter('');
                loadTasks();
            } else {
                const error = await response.json();
                alert(`Ошибка: ${error.error}`);
            }
        } catch (error) {
            console.error('Ошибка создания задачи:', error);
            alert('Ошибка создания задачи');
        } finally {
            setUploading(false);
        }
    };

    const loadTaskDetails = async (taskId) => {
        try {
            const response = await fetch(`${API_BASE}/price-list-tasks/${taskId}/`, {
                headers: {
                    'Authorization': `Token ${token}`,
                    'Content-Type': 'application/json'
                }
            });
            
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
            const response = await fetch(`${API_BASE}/price-list-tasks/${taskId}/items/?page=${page}&page_size=50`, {
                headers: {
                    'Authorization': `Token ${token}`,
                    'Content-Type': 'application/json'
                }
            });
            
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
            const response = await fetch(`${API_BASE}/price-list-tasks/${taskId}/download/`, {
                headers: {
                    'Authorization': `Token ${token}`
                }
            });
            
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
            alert('Ошибка скачивания файла');
        }
    };

    const deleteTask = async (taskId) => {
        if (!confirm('Вы уверены, что хотите удалить эту задачу?')) {
            return;
        }

        try {
            const response = await fetch(`${API_BASE}/price-list-tasks/${taskId}/delete/`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Token ${token}`,
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                alert('Задача удалена');
                loadTasks();
                if (selectedTask && selectedTask.id === taskId) {
                    setSelectedTask(null);
                    setTaskItems([]);
                }
            }
        } catch (error) {
            console.error('Ошибка удаления:', error);
            alert('Ошибка удаления задачи');
        }
    };

    const getStatusColor = (status) => {
        switch (status) {
            case 'completed': return 'text-green-600';
            case 'processing': return 'text-blue-600';
            case 'failed': return 'text-red-600';
            default: return 'text-gray-600';
        }
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
        <div className="container mx-auto px-4 py-8">
            <h1 className="text-3xl font-bold mb-8">Анализ прайс-листа на площадках</h1>
            
            {/* Форма загрузки */}
            <div className="bg-white rounded-lg shadow-md p-6 mb-8">
                <h2 className="text-xl font-semibold mb-4">Загрузить прайс-лист для анализа</h2>
                
                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium mb-2">Файл прайс-листа (Excel)</label>
                        <input
                            type="file"
                            accept=".xlsx,.xls"
                            onChange={handleFileChange}
                            className="w-full p-2 border border-gray-300 rounded"
                            required
                        />
                    </div>
                    
                    <div>
                        <label className="block text-sm font-medium mb-2">Площадка</label>
                        <select
                            value={platform}
                            onChange={(e) => setPlatform(e.target.value)}
                            className="w-full p-2 border border-gray-300 rounded"
                        >
                            <option value="autopiter">АвтоПитер</option>
                            <option value="emex">Емекс</option>
                            <option value="armtek">Армтек</option>
                        </select>
                    </div>
                    
                    <div>
                        <label className="block text-sm font-medium mb-2">Фильтр бренда конкурента (необязательно)</label>
                        <input
                            type="text"
                            value={competitorBrandFilter}
                            onChange={(e) => setCompetitorBrandFilter(e.target.value)}
                            placeholder="Например: Ootoko"
                            className="w-full p-2 border border-gray-300 rounded"
                        />
                    </div>
                    
                    <div className="flex items-center">
                        <input
                            type="checkbox"
                            id="includePriceAnalysis"
                            checked={includePriceAnalysis}
                            onChange={(e) => setIncludePriceAnalysis(e.target.checked)}
                            className="mr-2"
                        />
                        <label htmlFor="includePriceAnalysis">Включить анализ цен</label>
                    </div>
                    
                    <button
                        type="submit"
                        disabled={uploading}
                        className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                        {uploading ? 'Загрузка...' : 'Создать задачу'}
                    </button>
                </form>
            </div>
            
            {/* Список задач */}
            <div className="bg-white rounded-lg shadow-md p-6">
                <h2 className="text-xl font-semibold mb-4">Задачи анализа</h2>
                
                {loading ? (
                    <p>Загрузка...</p>
                ) : tasks.length === 0 ? (
                    <p>Нет задач анализа</p>
                ) : (
                    <div className="space-y-4">
                        {tasks.map((task) => (
                            <div key={task.id} className="border border-gray-200 rounded p-4">
                                <div className="flex justify-between items-start">
                                    <div className="flex-1">
                                        <h3 className="font-semibold">
                                            Задача #{task.id} - {getPlatformName(task.platform)}
                                        </h3>
                                        <p className="text-sm text-gray-600">
                                            Создана: {new Date(task.created_at).toLocaleString()}
                                        </p>
                                        <p className={`text-sm ${getStatusColor(task.status)}`}>
                                            Статус: {task.status}
                                        </p>
                                        {task.processed_items > 0 && (
                                            <p className="text-sm">
                                                Прогресс: {task.processed_items}/{task.total_items} 
                                                (Найдено: {task.found_items}, Не найдено: {task.not_found_items})
                                            </p>
                                        )}
                                    </div>
                                    
                                    <div className="flex space-x-2">
                                        <button
                                            onClick={() => loadTaskDetails(task.id)}
                                            className="bg-gray-600 text-white px-3 py-1 rounded text-sm hover:bg-gray-700"
                                        >
                                            Детали
                                        </button>
                                        
                                        {task.has_result_file && (
                                            <button
                                                onClick={() => downloadResult(task.id)}
                                                className="bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700"
                                            >
                                                Скачать
                                            </button>
                                        )}
                                        
                                        <button
                                            onClick={() => deleteTask(task.id)}
                                            className="bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700"
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
                <div className="bg-white rounded-lg shadow-md p-6 mt-8">
                    <h2 className="text-xl font-semibold mb-4">
                        Детали задачи #{selectedTask.id}
                    </h2>
                    
                    <div className="grid grid-cols-2 gap-4 mb-6">
                        <div>
                            <p><strong>Площадка:</strong> {selectedTask.platform}</p>
                            <p><strong>Статус:</strong> {selectedTask.status}</p>
                            <p><strong>Создана:</strong> {new Date(selectedTask.created_at).toLocaleString()}</p>
                        </div>
                        <div>
                            <p><strong>Всего позиций:</strong> {selectedTask.total_items}</p>
                            <p><strong>Обработано:</strong> {selectedTask.processed_items}</p>
                            <p><strong>Найдено:</strong> {selectedTask.found_items}</p>
                            <p><strong>Не найдено:</strong> {selectedTask.not_found_items}</p>
                        </div>
                    </div>
                    
                    {selectedTask.log && (
                        <div className="mb-6">
                            <h3 className="font-semibold mb-2">Лог выполнения:</h3>
                            <div className="bg-gray-100 p-4 rounded max-h-60 overflow-y-auto">
                                <pre className="text-sm whitespace-pre-wrap">{selectedTask.log}</pre>
                            </div>
                        </div>
                    )}
                    
                    {/* Список позиций */}
                    <div>
                        <h3 className="font-semibold mb-4">Позиции ({taskItems.length})</h3>
                        
                        <div className="overflow-x-auto">
                            <table className="min-w-full border border-gray-200">
                                <thead>
                                    <tr className="bg-gray-50">
                                        <th className="border p-2 text-left">Бренд</th>
                                        <th className="border p-2 text-left">Артикул</th>
                                        <th className="border p-2 text-left">Наименование</th>
                                        <th className="border p-2 text-left">Наличие</th>
                                        <th className="border p-2 text-left">Наша цена</th>
                                        <th className="border p-2 text-left">Мин. цена конкурента</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {taskItems.map((item) => (
                                        <tr key={item.id}>
                                            <td className="border p-2">{item.manufacturer}</td>
                                            <td className="border p-2">{item.article}</td>
                                            <td className="border p-2">{item.nomenclature}</td>
                                            <td className="border p-2">
                                                <span className={`px-2 py-1 rounded text-sm ${
                                                    item.is_found 
                                                        ? 'bg-green-100 text-green-800' 
                                                        : 'bg-red-100 text-red-800'
                                                }`}>
                                                    {item.is_found ? 'выгружено' : 'НЕТ'}
                                                </span>
                                            </td>
                                            <td className="border p-2">
                                                {item.marketplace_price ? `${item.marketplace_price} ₽` : ''}
                                            </td>
                                            <td className="border p-2">
                                                {item.min_competitor_price ? `${item.min_competitor_price} ₽` : ''}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        
                        {/* Пагинация */}
                        {totalPages > 1 && (
                            <div className="flex justify-center mt-4 space-x-2">
                                <button
                                    onClick={() => loadTaskItems(selectedTask.id, currentPage - 1)}
                                    disabled={currentPage === 1}
                                    className="px-3 py-1 border rounded disabled:opacity-50"
                                >
                                    Назад
                                </button>
                                <span className="px-3 py-1">
                                    Страница {currentPage} из {totalPages}
                                </span>
                                <button
                                    onClick={() => loadTaskItems(selectedTask.id, currentPage + 1)}
                                    disabled={currentPage === totalPages}
                                    className="px-3 py-1 border rounded disabled:opacity-50"
                                >
                                    Вперед
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

export default PriceListAnalysis;
