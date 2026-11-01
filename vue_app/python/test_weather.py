from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
import weather

class WeatherTests(unittest.TestCase):
    def test_defaults_cache_and_offline_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertFalse(weather.current(root)['configured'])
            payload=dict(current=dict(temperature_2m=10.4,weather_code=0,is_day=0,time='2026-11-02T03:30'))
            with patch('weather.fetch',return_value=payload) as fetch:
                value=weather.current(root,default_location=weather.DEFAULT_LOCATION)
                self.assertEqual(value['location']['name'],'焦作市');self.assertEqual(value['temperature'],10.4);self.assertEqual(value['emoji'],'🌙')
                self.assertFalse(weather.current(root)['stale']);self.assertEqual(fetch.call_count,1)
            with patch('weather.fetch',side_effect=OSError('offline')):
                self.assertTrue(weather.current(root,force=True)['stale'])
            weather.choose(root,dict(name='测试城市',latitude=30,longitude=110))
            with patch('weather.fetch',side_effect=OSError('offline')):
                with self.assertRaisesRegex(ValueError,'暂时无法更新'):weather.current(root)
    def test_invalid_location_and_city_queries(self):
        with self.assertRaises(ValueError):weather.location(dict(name='错误',latitude=100,longitude=0))
        with self.assertRaises(ValueError):weather.search('焦')
        self.assertEqual(weather.search('焦作')[0]['name'],'焦作市')
    def test_weather_symbols_follow_reported_conditions(self):
        self.assertEqual(weather.describe(61)[0],'雨');self.assertEqual(weather.describe(95)[1],'⛈️');self.assertEqual(weather.describe(75)[1],'❄️')

if __name__=='__main__':unittest.main()
