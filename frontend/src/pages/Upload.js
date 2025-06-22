import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

function Upload() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0];
    if (selectedFile && selectedFile.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') {
      setFile(selectedFile);
      setError(null);
    } else {
      setError('Пожалуйста, выберите файл Excel (.xlsx)');
      setFile(null);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) return;

    setLoading(true);
    setError(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await axios.post('http://localhost:8000/api/parsing-tasks/', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
          'Authorization': `Token ${localStorage.getItem('token')}`
        }
      });

      navigate(`/tasks/${response.data.id}`);
    } catch (err) {
      setError(err.response?.data?.message || 'Произошла ошибка при загрузке файла');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white shadow sm:rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg font-medium leading-6 text-gray-900">
            Загрузка файла с данными
          </h3>
          <div className="mt-2 max-w-xl text-sm text-gray-500">
            <p>Загрузите Excel-файл с данными запчастей для обработки.</p>
          </div>
          <form onSubmit={handleSubmit} className="mt-5">
            <div className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-gray-300 border-dashed rounded-md">
              <div className="space-y-1 text-center">
                <svg
                  className="mx-auto h-12 w-12 text-gray-400"
                  stroke="currentColor"
                  fill="none"
                  viewBox="0 0 48 48"
                  aria-hidden="true"
                >
                  <path
                    d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <div className="flex text-sm text-gray-600">
                  <label
                    htmlFor="file-upload"
                    className="relative cursor-pointer bg-white rounded-md font-medium text-blue-600 hover:text-blue-500 focus-within:outline-none focus-within:ring-2 focus-within:ring-offset-2 focus-within:ring-blue-500"
                  >
                    <span>Загрузить файл</span>
                    <input
                      id="file-upload"
                      name="file-upload"
                      type="file"
                      className="sr-only"
                      accept=".xlsx"
                      onChange={handleFileChange}
                    />
                  </label>
                  <p className="pl-1">или перетащите</p>
                </div>
                <p className="text-xs text-gray-500">Excel файл (.xlsx)</p>
              </div>
            </div>
            {file && (
              <div className="mt-4 text-sm text-gray-500">
                Выбран файл: {file.name}
              </div>
            )}
            {error && (
              <div className="mt-4 text-sm text-red-600">
                {error}
              </div>
            )}
            <div className="mt-5">
              <button
                type="submit"
                disabled={!file || loading}
                className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
                  !file || loading
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500'
                }`}
              >
                {loading ? 'Загрузка...' : 'Начать обработку'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

export default Upload; 