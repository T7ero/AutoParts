import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';

function Tasks() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { taskId } = useParams();
  const [logModal, setLogModal] = useState({ open: false, log: '', taskId: null });

  useEffect(() => {
    fetchTasks();
  }, []);

  const fetchTasks = async () => {
    try {
      const response = await axios.get('http://localhost:8000/api/parsing-tasks/', {
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
          const response = await axios.get(`http://localhost:8000/api/parsing-tasks/${taskId}/status/`, {
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
          const response = await axios.get('http://localhost:8000/api/parsing-tasks/', {
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

  const clearTasks = async () => {
    if (window.confirm('Вы уверены, что хотите очистить все задачи?')) {
      try {
        await fetch('http://localhost:8000/api/parsing-tasks/clear/', {
          method: 'DELETE',
          headers: {
            'Authorization': `Token ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          }
        });
        fetchTasks(); // Обновляем список задач после очистки
      } catch (err) {
        console.error('Ошибка при очистке задач:', err);
        setError('Не удалось очистить задачи');
      }
    }
  };

  const handleShowLog = async (id) => {
    setLogModal({ open: true, log: 'Загрузка...', taskId: id });
    try {
      const response = await axios.get(`http://localhost:8000/api/parsing-tasks/${id}/log/`, {
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
                <div className="mt-2">
                  <button
                    className="text-xs text-gray-500 underline hover:text-blue-600"
                    onClick={() => handleShowLog(task.id)}
                  >
                    Показать лог задачи
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