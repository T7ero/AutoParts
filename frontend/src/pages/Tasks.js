import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { taskId } = useParams();
  const [logModal, setLogModal] = useState({ open: false, log: '', taskId: null });
  const [activeTab, setActiveTab] = useState('tasks'); // 'tasks' или 'logs'
  const [logs, setLogs] = useState({});
  const [logsLoading, setLogsLoading] = useState(false);

  useEffect(() => {
    fetchTasks();
  }, []);

  useEffect(() => {
    if (activeTab === 'logs') {
      fetchLogs();
    }
  }, [activeTab, fetchLogs]);

  useEffect(() => {
    let interval;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const response = await axios.get(`/api/parsing-tasks/${taskId}/status/`, {
            headers: {
              'Authorization': `Token ${localStorage.getItem('token')}`
            }
          });
          
          setTasks(prevTasks => 
            prevTasks.map(task => 
              task.id === parseInt(taskId) 
                ? { ...task, ...response.data }
                : task
            )
          );

          if (response.data.status === 'completed' || response.data.status === 'failed') {
            clearInterval(interval);
          }
        } catch (err) {
          console.error('Ошибка при обновлении статуса:', err);
        }
      }, 5000);
    } else {
      // Автообновление списка задач, если есть незавершённые задачи
      interval = setInterval(async () => {
        try {
          const response = await axios.get('/api/parsing-tasks/', {
            headers: {
              'Authorization': `Token ${localStorage.getItem('token')}`
            }
          });
          setTasks(response.data);
          
          // Автообновление логов для вкладки "Логи"
          if (activeTab === 'logs') {
            setTimeout(() => refreshLogs(), 1000); // Небольшая задержка
          }
        } catch (err) {
          // ignore
        }
      }, 5000);
    }

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [taskId, activeTab, refreshLogs]);

  const fetchTasks = async () => {
    try {
      const response = await axios.get('/api/parsing-tasks/', {
        headers: {
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });
      setTasks(response.data);
    } catch (err) {
      setError('Ошибка при загрузке задач');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let interval;
    if (taskId) {
      interval = setInterval(async () => {
        try {
          const response = await axios.get(`/api/parsing-tasks/${taskId}/status/`, {
            headers: {
              'Authorization': `Token ${localStorage.getItem('token')}`
            }
          });
          
          setTasks(prevTasks => 
            prevTasks.map(task => 
              task.id === parseInt(taskId) 
                ? { ...task, ...response.data }
                : task
            )
          );

          if (response.data.status === 'completed' || response.data.status === 'failed') {
            clearInterval(interval);
          }
        } catch (err) {
          console.error('Ошибка при обновлении статуса:', err);
        }
      }, 5000);
    } else {
      // Автообновление списка задач, если есть незавершённые задачи
      interval = setInterval(async () => {
        try {
          const response = await axios.get('/api/parsing-tasks/', {
            headers: {
              'Authorization': `Token ${localStorage.getItem('token')}`
            }
          });
          setTasks(response.data);
          
          // Автообновление логов для вкладки "Логи"
          if (activeTab === 'logs') {
            setTimeout(() => refreshLogs(), 1000); // Небольшая задержка
          }
        } catch (err) {
          // ignore
        }
      }, 5000);
    }

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [taskId, activeTab, refreshLogs]);

  const clearTasks = async () => {
    if (window.confirm('Вы уверены, что хотите очистить все задачи? Счетчик задач будет сброшен на 1.')) {
      try {
        const response = await fetch('/api/parsing-tasks/clear/', {
          method: 'DELETE',
          headers: {
            'Authorization': `Token ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          }
        });
        
        if (response.ok) {
          fetchTasks(); // Обновляем список задач после очистки
        } else {
          setError('Не удалось очистить задачи');
        }
      } catch (err) {
        console.error('Ошибка при очистке задач:', err);
        setError('Не удалось очистить задачи');
      }
    }
  };

  const deleteTask = async (taskId) => {
    if (window.confirm(`Вы уверены, что хотите удалить задачу #${taskId}?`)) {
      try {
        const response = await fetch(`/api/parsing-tasks/${taskId}/delete/`, {
          method: 'DELETE',
          headers: {
            'Authorization': `Token ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          }
        });
        
        if (response.ok) {
          fetchTasks(); // Обновляем список задач после удаления
        } else {
          setError('Не удалось удалить задачу');
        }
      } catch (err) {
        console.error('Ошибка при удалении задачи:', err);
        setError('Не удалось удалить задачу');
      }
    }
  };

  const handleShowLog = async (id) => {
    setLogModal({ open: true, log: 'Загрузка...', taskId: id });
    try {
      const response = await axios.get(`/api/parsing-tasks/${id}/log/`, {
        headers: {
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });
      setLogModal({ open: true, log: response.data.log || 'Лог пуст', taskId: id });
    } catch (err) {
      setLogModal({ open: true, log: 'Ошибка при загрузке лога', taskId: id });
    }
  };

  const handleCloseLog = () => {
    setLogModal({ open: false, log: '', taskId: null });
  };

  const fetchLogs = useCallback(async () => {
    setLogsLoading(true);
    try {
      const logsData = {};
      for (const task of tasks) {
        if (task.status === 'in_progress' || task.status === 'completed') {
          try {
            const response = await axios.get(`/api/parsing-tasks/${task.id}/log/`, {
              headers: {
                'Authorization': `Token ${localStorage.getItem('token')}`
              }
            });
            logsData[task.id] = response.data.log || 'Лог пуст';
          } catch (err) {
            logsData[task.id] = 'Ошибка при загрузке лога';
          }
        }
      }
      setLogs(logsData);
    } catch (err) {
      console.error('Ошибка при загрузке логов:', err);
    } finally {
      setLogsLoading(false);
    }
  }, [tasks]);

  const refreshLogs = useCallback(() => {
    if (activeTab === 'logs') {
      fetchLogs();
    }
  }, [activeTab, fetchLogs]);

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center text-red-600">
        {error}
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto">
      {/* Вкладки */}
      <div className="border-b border-gray-200 mb-6">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('tasks')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'tasks'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Задачи
          </button>
          <button
            onClick={() => setActiveTab('logs')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'logs'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            Логи
          </button>
        </nav>
      </div>

      {/* Содержимое вкладки "Задачи" */}
      {activeTab === 'tasks' && (
        <>
          <div className="flex justify-end mb-4">
            <button
              onClick={clearTasks}
              className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
            >
              Очистить все задачи
            </button>
          </div>
          
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <ul className="divide-y divide-gray-200">
              {tasks.map((task) => (
                <li key={task.id}>
                  <div className="px-4 py-4 sm:px-6">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center">
                        <p className="text-sm font-medium text-blue-600 truncate">
                          Задача #{task.id}
                        </p>
                        <div className="ml-2 flex-shrink-0 flex">
                          <p className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                            task.status === 'completed' ? 'bg-green-100 text-green-800' :
                            task.status === 'failed' ? 'bg-red-100 text-red-800' :
                            task.status === 'in_progress' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {task.status === 'completed' ? 'Завершено' :
                             task.status === 'failed' ? 'Ошибка' :
                             task.status === 'in_progress' ? 'В процессе' :
                             'Ожидает'}
                          </p>
                        </div>
                      </div>
                      <div className="ml-2 flex-shrink-0 flex">
                        <p className="text-sm text-gray-500">
                          {new Date(task.created_at).toLocaleString()}
                        </p>
                      </div>
                    </div>
                    <div className="mt-2 sm:flex sm:justify-between">
                      <div className="sm:flex">
                        <p className="flex items-center text-sm text-gray-500">
                          {task.file}
                        </p>
                      </div>
                      {(task.progress > 0 && task.progress < 100) && (
                        <div className="mt-2 flex items-center text-sm text-gray-500 sm:mt-0">
                          <div className="w-full bg-gray-200 rounded-full h-2.5">
                            <div
                              className="bg-blue-600 h-2.5 rounded-full"
                              style={{ width: `${task.progress}%` }}
                            ></div>
                          </div>
                          <span className="ml-2">{task.progress}%</span>
                        </div>
                      )}
                    </div>
                    {task.error_message && (
                      <div className="mt-2 text-sm text-red-600">
                        {task.error_message}
                      </div>
                    )}
                    {/* Кнопка для показа лога */}
                    <div className="mt-2 flex justify-between items-center">
                      <button
                        className="text-xs text-gray-500 underline hover:text-blue-600"
                        onClick={() => handleShowLog(task.id)}
                      >
                        Показать лог задачи
                      </button>
                      <button
                        className="text-xs text-red-500 underline hover:text-red-700"
                        onClick={() => deleteTask(task.id)}
                      >
                        Удалить задачу
                      </button>
                    </div>
                    {/* Ссылки на все выгруженные файлы */}
                    {task.status === 'completed' && task.result_files && (
                      <div className="mt-2 flex flex-col gap-1">
                        <span className="text-xs text-gray-500">Файлы результатов:</span>
                        {Object.entries(task.result_files).map(([site, path]) => (
                          <a
                            key={site}
                            href={`/${path.replace(/\\/g, '/')}`}
                            className="text-sm font-medium text-blue-600 hover:text-blue-500"
                            download
                          >
                            {site === 'autopiter' && 'Autopiter'}
                            {site === 'emex' && 'Emex'}
                            {site === 'armtek' && 'Armtek'}
                            {!['autopiter','emex','armtek'].includes(site) && site}
                          </a>
                        ))}
                      </div>
                    )}
                    {task.status === 'completed' && task.result_file && (
                      <div className="mt-2">
                        <a
                          href={task.result_file}
                          className="text-sm font-medium text-blue-600 hover:text-blue-500"
                          download
                        >
                          Скачать результат
                        </a>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}

      {/* Содержимое вкладки "Логи" */}
      {activeTab === 'logs' && (
        <>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-medium text-gray-900">Логи задач в реальном времени</h2>
            <button
              onClick={refreshLogs}
              disabled={logsLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              {logsLoading ? 'Обновление...' : 'Обновить логи'}
            </button>
          </div>
          
          <div className="bg-white shadow overflow-hidden sm:rounded-md">
            <div className="px-4 py-4">
              {logsLoading ? (
                <div className="flex justify-center items-center h-32">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                </div>
              ) : Object.keys(logs).length === 0 ? (
                <p className="text-gray-500 text-center py-8">Нет доступных логов</p>
              ) : (
                <div className="space-y-4">
                  {Object.entries(logs).map(([taskId, log]) => {
                    const task = tasks.find(t => t.id === parseInt(taskId));
                    return (
                      <div key={taskId} className="border rounded-lg p-4">
                        <div className="flex justify-between items-center mb-2">
                          <h3 className="text-sm font-medium text-gray-900">
                            Задача #{taskId} - {task ? task.file : 'Неизвестный файл'}
                          </h3>
                          <span className={`px-2 py-1 text-xs font-semibold rounded-full ${
                            task?.status === 'completed' ? 'bg-green-100 text-green-800' :
                            task?.status === 'failed' ? 'bg-red-100 text-red-800' :
                            task?.status === 'in_progress' ? 'bg-yellow-100 text-yellow-800' :
                            'bg-gray-100 text-gray-800'
                          }`}>
                            {task?.status === 'completed' ? 'Завершено' :
                             task?.status === 'failed' ? 'Ошибка' :
                             task?.status === 'in_progress' ? 'В процессе' :
                             'Ожидает'}
                          </span>
                        </div>
                        <pre className="bg-gray-100 p-3 rounded text-xs max-h-64 overflow-auto whitespace-pre-wrap font-mono">
                          {log}
                        </pre>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* Модальное окно для лога */}
      {logModal.open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-40">
          <div className="bg-white rounded-lg shadow-lg max-w-2xl w-full p-6 relative">
            <button
              className="absolute top-2 right-2 text-gray-400 hover:text-gray-700"
              onClick={handleCloseLog}
            >
              ×
            </button>
            <h2 className="text-lg font-bold mb-2">Лог задачи #{logModal.taskId}</h2>
            <pre className="bg-gray-100 p-2 rounded text-xs max-h-96 overflow-auto whitespace-pre-wrap">
              {logModal.log}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tasks;