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
                  {task.status === 'in_progress' && (
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
    </div>
  );
}

export default Tasks;