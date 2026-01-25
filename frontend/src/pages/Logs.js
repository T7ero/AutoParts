import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';

function Logs() {
  const [logs, setLogs] = useState({});
  const [tasks, setTasks] = useState([]);
  const [priceListTasks, setPriceListTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTask, setSelectedTask] = useState(null);
  const [selectedTaskType, setSelectedTaskType] = useState(null); // 'parsing' or 'price_list'
  const [autoScroll, setAutoScroll] = useState(true);
  const logsEndRef = useRef(null);

  useEffect(() => {
    fetchTasks();
    fetchPriceListTasks();
    const interval = setInterval(() => {
      fetchTasks();
      fetchPriceListTasks();
    }, 2000); // Обновляем каждые 2 секунды для более частого обновления прогресса
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedTask && selectedTaskType) {
      if (selectedTaskType === 'parsing') {
        fetchTaskLogs(selectedTask);
        const interval = setInterval(() => fetchTaskLogs(selectedTask), 2000); // Обновляем каждые 2 секунды
        return () => clearInterval(interval);
      } else if (selectedTaskType === 'price_list') {
        fetchPriceListTaskLogs(selectedTask);
        const interval = setInterval(() => fetchPriceListTaskLogs(selectedTask), 2000);
        return () => clearInterval(interval);
      }
    }
  }, [selectedTask, selectedTaskType]);

  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, autoScroll]);

  const fetchTasks = async () => {
    try {
      const response = await axios.get('/api/parsing-tasks/', {
        headers: {
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });
      setTasks(response.data);
      setLoading(false);
    } catch (err) {
      console.error('Ошибка при загрузке задач парсинга:', err);
      // Не устанавливаем ошибку, если это первая загрузка
      if (tasks.length === 0) {
        setError('Ошибка при загрузке задач');
        setLoading(false);
      }
    }
  };

  const fetchPriceListTasks = async () => {
    try {
      const response = await axios.get('/api/price-list-tasks/', {
        headers: {
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });
      setPriceListTasks(response.data);
    } catch (err) {
      console.error('Ошибка при загрузке задач анализа прайс-листа:', err);
    }
  };

  const fetchTaskLogs = async (taskId) => {
    try {
      const response = await axios.get(`/api/parsing-tasks/${taskId}/logs/`, {
        headers: {
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });
      setLogs(prev => ({
        ...prev,
        [`parsing_${taskId}`]: response.data.logs || []
      }));
      
      // Обновляем информацию о прогрессе задачи, если она есть в ответе
      if (response.data.progress) {
        setTasks(prevTasks => 
          prevTasks.map(task => 
            task.id === taskId 
              ? { 
                  ...task, 
                  current_row: response.data.progress.current_row,
                  total_rows: response.data.progress.total_rows,
                  processed_rows: response.data.progress.processed_rows,
                  progress: response.data.progress.progress_percent
                }
              : task
          )
        );
      }
    } catch (err) {
      console.error('Ошибка при загрузке логов:', err);
    }
  };

  const fetchPriceListTaskLogs = async (taskId) => {
    try {
      const response = await axios.get(`/api/price-list-tasks/${taskId}/logs/`, {
        headers: {
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });
      setLogs(prev => ({
        ...prev,
        [`price_list_${taskId}`]: response.data.logs || []
      }));
    } catch (err) {
      console.error('Ошибка при загрузке логов задачи анализа прайс-листа:', err);
    }
  };

  const handleTaskSelect = (taskId, taskType) => {
    setSelectedTask(taskId);
    setSelectedTaskType(taskType);
    const logKey = `${taskType}_${taskId}`;
    if (!logs[logKey]) {
      if (taskType === 'parsing') {
        fetchTaskLogs(taskId);
      } else if (taskType === 'price_list') {
        fetchPriceListTaskLogs(taskId);
      }
    }
  };

  const clearLogs = () => {
    setLogs({});
    setSelectedTask(null);
    setSelectedTaskType(null);
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString('ru-RU');
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'text-green-600 dark:text-green-400';
      case 'failed': return 'text-red-600 dark:text-red-400';
      case 'processing': return 'text-blue-600 dark:text-blue-400';
      case 'pending': return 'text-yellow-600 dark:text-yellow-400';
      default: return 'text-gray-600 dark:text-gray-400';
    }
  };

  const getStatusText = (status) => {
    switch (status) {
      case 'completed': return 'Завершено';
      case 'failed': return 'Ошибка';
      case 'processing': return 'Обработка';
      case 'pending': return 'Ожидание';
      default: return status;
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 dark:border-blue-400"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-100 dark:bg-red-900 border border-red-400 dark:border-red-700 text-red-700 dark:text-red-300 px-4 py-3 rounded">
        {error}
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto">
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg transition-colors">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex justify-between items-center">
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Логи задач</h1>
            <div className="flex space-x-2">
              <button
                onClick={clearLogs}
                className="px-4 py-2 bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
              >
                Очистить логи
              </button>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) => setAutoScroll(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm text-gray-600 dark:text-gray-300">Автопрокрутка</span>
              </label>
            </div>
          </div>
        </div>

        <div className="flex h-96">
          {/* Список задач */}
          <div className="w-1/3 border-r border-gray-200 dark:border-gray-700 overflow-y-auto">
            <div className="p-4">
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Задачи</h3>
              
              {/* Задачи анализа прайс-листа */}
              {priceListTasks.length > 0 && (
                <div className="mb-4">
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Анализ прайс-листа</h4>
                  <div className="space-y-2">
                    {priceListTasks.map((task) => (
                      <div
                        key={`price_list_${task.id}`}
                        onClick={() => handleTaskSelect(task.id, 'price_list')}
                        className={`p-3 rounded-lg cursor-pointer transition-colors ${
                          selectedTask === task.id && selectedTaskType === 'price_list'
                            ? 'bg-blue-100 dark:bg-blue-900 border-blue-300 dark:border-blue-600 border'
                            : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600'
                        }`}
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <h4 className="font-medium text-gray-900 dark:text-white">
                              Прайс-лист #{task.id}
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-300">
                              {task.platform || 'Не указано'}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              {formatTimestamp(task.created_at)}
                            </p>
                            {task.total_items > 0 && (
                              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                {task.processed_items}/{task.total_items} позиций
                              </p>
                            )}
                          </div>
                          <span className={`text-xs px-2 py-1 rounded-full ${getStatusColor(task.status)}`}>
                            {getStatusText(task.status)}
                          </span>
                        </div>
                        {task.total_items > 0 && (
                          <div className="mt-2">
                            <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                              <div
                                className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
                                style={{ width: `${(task.processed_items / task.total_items) * 100}%` }}
                              ></div>
                            </div>
                            <span className="text-xs text-gray-600 dark:text-gray-400">
                              {Math.round((task.processed_items / task.total_items) * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Задачи парсинга брендов */}
              {tasks.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Парсинг брендов</h4>
                  <div className="space-y-2">
                    {tasks.map((task) => (
                      <div
                        key={`parsing_${task.id}`}
                        onClick={() => handleTaskSelect(task.id, 'parsing')}
                        className={`p-3 rounded-lg cursor-pointer transition-colors ${
                          selectedTask === task.id && selectedTaskType === 'parsing'
                            ? 'bg-blue-100 dark:bg-blue-900 border-blue-300 dark:border-blue-600 border'
                            : 'bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600'
                        }`}
                      >
                        <div className="flex justify-between items-start">
                          <div>
                            <h4 className="font-medium text-gray-900 dark:text-white">
                              Задача #{task.id}
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-300">
                              {task.file_name || 'Без названия'}
                            </p>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              {formatTimestamp(task.created_at)}
                            </p>
                          </div>
                          <span className={`text-xs px-2 py-1 rounded-full ${getStatusColor(task.status)}`}>
                            {getStatusText(task.status)}
                          </span>
                        </div>
                        {(task.status === 'in_progress' || task.status === 'processing' || task.progress !== undefined) && (
                          <div className="mt-2">
                            <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                              <div
                                className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
                                style={{ width: `${task.progress !== undefined ? task.progress : 0}%` }}
                              ></div>
                            </div>
                            <div className="flex justify-between items-center mt-1">
                              <span className="text-xs text-gray-600 dark:text-gray-400">
                                {task.progress !== undefined ? `${task.progress}%` : '0%'}
                              </span>
                              {task.current_row && task.total_rows && (
                                <span className="text-xs text-gray-500 dark:text-gray-400">
                                  Строка {task.current_row} / {task.total_rows}
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {tasks.length === 0 && priceListTasks.length === 0 && (
                <p className="text-gray-500 dark:text-gray-400">Нет доступных задач</p>
              )}
            </div>
          </div>

          {/* Логи выбранной задачи */}
          <div className="w-2/3 p-4">
            {selectedTask ? (
              <div className="h-full flex flex-col">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                    {selectedTaskType === 'price_list' ? 'Логи анализа прайс-листа' : 'Логи задачи'} #{selectedTask}
                  </h3>
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    {logs[`${selectedTaskType}_${selectedTask}`]?.length || 0} записей
                  </span>
                </div>
                
                <div className="flex-1 flex flex-col">
                  {/* Информация о прогрессе для задач парсинга */}
                  {selectedTaskType === 'parsing' && tasks.find(t => t.id === selectedTask) && (() => {
                    const task = tasks.find(t => t.id === selectedTask);
                    if (task && (task.status === 'in_progress' || task.status === 'processing' || task.progress > 0)) {
                      return (
                        <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                          <div className="flex justify-between items-center mb-2">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                              Прогресс выполнения
                            </span>
                            <span className="text-sm text-gray-600 dark:text-gray-400">
                              {task.progress !== undefined ? `${task.progress}%` : '0%'}
                            </span>
                          </div>
                          <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2 mb-2">
                            <div
                              className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
                              style={{ width: `${task.progress !== undefined ? task.progress : 0}%` }}
                            ></div>
                          </div>
                          {task.current_row && task.total_rows && (
                            <p className="text-xs text-gray-600 dark:text-gray-400">
                              Обрабатывается строка <span className="font-semibold">{task.current_row}</span> из <span className="font-semibold">{task.total_rows}</span>
                            </p>
                          )}
                        </div>
                      );
                    }
                    return null;
                  })()}
                  
                  <div className="flex-1 bg-gray-900 text-green-400 p-4 rounded-lg overflow-y-auto font-mono text-sm">
                    {logs[`${selectedTaskType}_${selectedTask}`] && logs[`${selectedTaskType}_${selectedTask}`].length > 0 ? (
                      logs[`${selectedTaskType}_${selectedTask}`].map((log, index) => (
                        <div key={index} className="mb-1">
                          <span className="text-gray-400">[{formatTimestamp(log.timestamp)}]</span>
                          <span className="ml-2">{log.message}</span>
                        </div>
                      ))
                    ) : (
                      <div className="text-gray-500">Логи не найдены</div>
                    )}
                    <div ref={logsEndRef} />
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400">
                Выберите задачу для просмотра логов
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default Logs;

