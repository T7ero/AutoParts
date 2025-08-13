import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { taskId } = useParams();

  useEffect(() => {
    fetchTasks();
  }, []);

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
  }, [taskId]);

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

  const handleDeleteTask = async (taskId) => {
    if (window.confirm('Вы уверены, что хотите удалить эту задачу?')) {
      try {
        await axios.delete(`/api/parsing-tasks/${taskId}/delete/`, {
          headers: {
            'Authorization': `Token ${localStorage.getItem('token')}`
          }
        });
        fetchTasks();
      } catch (err) {
        alert('Ошибка при удалении задачи');
      }
    }
  };

  const handleClearAllTasks = async () => {
    if (window.confirm('Вы уверены, что хотите удалить все задачи?')) {
      try {
        await axios.delete('/api/parsing-tasks/clear/', {
          headers: {
            'Authorization': `Token ${localStorage.getItem('token')}`
          }
        });
        fetchTasks();
      } catch (err) {
        alert('Ошибка при очистке задач');
      }
    }
  };

  const handleDownloadResult = async (task) => {
    if (task.status === 'completed' && task.result_file) {
      try {
        const response = await axios.get(`/api/parsing-tasks/${task.id}/download/`, {
          headers: {
            'Authorization': `Token ${localStorage.getItem('token')}`
          },
          responseType: 'blob'
        });
        
        const url = window.URL.createObjectURL(new Blob([response.data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `result_${task.id}.xlsx`);
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
      } catch (err) {
        alert('Ошибка при скачивании результата');
      }
    }
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

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleString('ru-RU');
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
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Задачи парсинга</h1>
            <div className="flex space-x-2">
              <button
                onClick={handleClearAllTasks}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
              >
                Очистить все
              </button>
            </div>
          </div>
        </div>

        <div className="p-6">
          {tasks.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-gray-500 dark:text-gray-400 text-lg">Нет доступных задач</p>
              <p className="text-gray-400 dark:text-gray-500 mt-2">Загрузите файл для создания новой задачи</p>
            </div>
          ) : (
            <div className="space-y-4">
              {tasks.map((task) => (
                <div key={task.id} className="border border-gray-200 dark:border-gray-600 rounded-lg p-4 hover:shadow-md transition-all bg-white dark:bg-gray-700">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center space-x-3">
                        <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                          Задача #{task.id}
                        </h3>
                        <span className={`px-2 py-1 text-xs rounded-full ${getStatusColor(task.status)}`}>
                          {getStatusText(task.status)}
                        </span>
                      </div>
                      
                      <div className="mt-2 space-y-1">
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                          <span className="font-medium">Файл:</span> {task.file_name || 'Не указан'}
                        </p>
                        <p className="text-sm text-gray-600 dark:text-gray-300">
                          <span className="font-medium">Создана:</span> {formatTimestamp(task.created_at)}
                        </p>
                        {task.updated_at && (
                          <p className="text-sm text-gray-600 dark:text-gray-300">
                            <span className="font-medium">Обновлена:</span> {formatTimestamp(task.updated_at)}
                          </p>
                        )}
                        {task.error_message && (
                          <p className="text-sm text-red-600 dark:text-red-400">
                            <span className="font-medium">Ошибка:</span> {task.error_message}
                          </p>
                        )}
                      </div>

                      {task.progress !== undefined && (
                        <div className="mt-3">
                          <div className="flex justify-between text-sm text-gray-600 dark:text-gray-300 mb-1">
                            <span>Прогресс</span>
                            <span>{task.progress}%</span>
                          </div>
                          <div className="w-full bg-gray-200 dark:bg-gray-600 rounded-full h-2">
                            <div
                              className="bg-blue-600 dark:bg-blue-400 h-2 rounded-full transition-all duration-300"
                              style={{ width: `${task.progress}%` }}
                            ></div>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col space-y-2 ml-4">
                      {task.status === 'completed' && (
                        <button
                          onClick={() => handleDownloadResult(task)}
                          className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors text-sm"
                        >
                          Скачать результат
                        </button>
                      )}
                      
                      <button
                        onClick={() => handleDeleteTask(task.id)}
                        className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors text-sm"
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
      </div>
    </div>
  );
}

export default Tasks;